import json

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _, ngettext
from django.views import View
from django.views.generic import DeleteView, DetailView, FormView, ListView, TemplateView
from eventyay.base.services.system_questions import (
    STATE_REQUIRED,
    get_system_question_base_state,
)
from eventyay.base.templatetags.rich_text import rich_text
from eventyay.control.permissions import EventPermissionRequiredMixin
from eventyay.control.views import CreateView, UpdateView

from . import mail as mail_helpers
from .forms import (
    CallSettingsForm,
    ExhibitionComposeForm,
    ExhibitionEmailQueueForm,
    ExhibitionMailTemplatesForm,
    ExhibitionProposalExtraLinkFormSet,
    ExhibitionProposalForm,
    ExhibitionProposalReviewForm,
    ExhibitionProposalReviewNotesForm,
    ExhibitionProposalSocialLinkFormSet,
    ExhibitionQuestionForm,
    ExhibitorExtraLinkFormSet,
    ExhibitorInfoForm,
    ExhibitorSocialLinkFormSet,
    SponsorGroupForm,
    social_link_prefixes,
)
from .models import (
    PROPOSAL_DEFAULT_FIELD_KEYS,
    PROPOSAL_DEFAULT_FIELDS,
    PROPOSAL_FORMSET_FIELD_KEYS,
    ExhibitionEmailQueue,
    ExhibitionProposal,
    ExhibitionProposalState,
    ExhibitionQuestion,
    ExhibitorInfo,
    ExhibitorSettings,
    SponsorGroup,
    generate_booth_id,
    get_next_sponsor_group_level,
)
from .social_links import serialize_social_link
from .utils import (
    add_external_image_csp_sources,
    build_exhibitor_video_embed,
    public_exhibitors_queryset,
    should_hide_applicant_emails,
)


def event_kwargs(event):
    return {
        "organizer": event.organizer.slug,
        "event": event.slug,
    }


def call_access_session_key(event):
    return f"exhibition_call_access_{event.pk}"


def partner_list_url(event, partner_type):
    """URL of the Sponsors or Exhibitors list, defaulting to Exhibitors."""
    route = {
        "sponsor": "plugins:exhibition:sponsors",
        "exhibitor": "plugins:exhibition:exhibitors",
    }.get(partner_type, "plugins:exhibition:exhibitors")
    return reverse(route, kwargs=event_kwargs(event))


def send_proposal_confirmation(event, proposal, requestor):
    """Send the submission confirmation email once the transaction commits."""
    transaction.on_commit(
        lambda: mail_helpers.queue_proposal_email(
            event,
            proposal,
            mail_helpers.PROPOSAL_NEW,
            send_now=True,
            requestor=requestor,
        )
    )


def queue_exhibitor_access_mail(event, exhibitor, requestor):
    """Queue the access-credentials email for organiser review in the outbox."""
    return mail_helpers.queue_exhibitor_access_email(event, exhibitor, requestor=requestor)


def partner_type_of(exhibitor):
    if exhibitor.is_sponsor and exhibitor.is_exhibitor:
        return "both"
    if exhibitor.is_sponsor:
        return "sponsor"
    if exhibitor.is_exhibitor:
        return "exhibitor"
    return None


class PublicEventLoginRequiredMixin(LoginRequiredMixin):
    def get_login_url(self):
        return reverse("cfp:event.login", kwargs=event_kwargs(self.request.event))


class PublicCallEnabledMixin:
    hide_after_deadline = False
    enforce_private = False

    def get_exhibition_settings(self):
        return ExhibitorSettings.objects.get_or_create(event=self.request.event)[0]

    def has_private_call_access(self, settings):
        return self.request.session.get(call_access_session_key(self.request.event)) == settings.call_secret

    def dispatch(self, request, *args, **kwargs):
        settings = self.get_exhibition_settings()
        if not settings.call_enabled:
            raise Http404()
        if self.hide_after_deadline and settings.call_hide_after_deadline and not settings.call_is_open:
            raise Http404()
        if self.enforce_private and settings.call_private and not self.has_private_call_access(settings):
            raise Http404()
        return super().dispatch(request, *args, **kwargs)


class SettingsView(EventPermissionRequiredMixin, ListView):
    model = ExhibitorInfo
    template_name = "exhibitors/settings.html"
    context_object_name = "exhibitors"
    permission = "can_change_settings"
    active_tab = "exhibitors"

    def get_queryset(self):
        return ExhibitorInfo.objects.filter(event=self.request.event)

    def get_active_tab(self):
        tab = self.request.GET.get("tab") or self.request.POST.get("tab") or self.active_tab
        if tab not in {"exhibitors", "sponsors", "call"}:
            return "exhibitors"
        return tab

    def get_settings_url(self, tab):
        route_names = {
            "call": "plugins:exhibition:settings.call",
            "sponsors": "plugins:exhibition:settings.sponsors",
        }
        route_name = route_names.get(tab, "plugins:exhibition:settings.exhibitors")
        return reverse(
            route_name,
            kwargs=event_kwargs(self.request.event),
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        settings = ExhibitorSettings.objects.get_or_create(event=self.request.event)[0]
        ctx["settings"] = settings
        ctx["data_access_fields"] = self.get_data_access_fields(settings)
        ctx["active_tab"] = self.get_active_tab()

        edit_group_forms = kwargs.get("edit_group_forms", {})
        sponsor_groups = list(
            SponsorGroup.objects.filter(event=self.request.event)
            .annotate(partner_count=Count("partners"))
            .order_by("level", "pk")
        )
        for group in sponsor_groups:
            group.edit_form = edit_group_forms.get(group.pk) or SponsorGroupForm(
                instance=group,
                event=self.request.event,
                prefix=f"group-{group.pk}",
            )

        ctx["sponsor_groups"] = sponsor_groups
        ctx["add_group_form"] = kwargs.get("add_group_form") or SponsorGroupForm(
            event=self.request.event,
            initial={"level": self.get_next_sponsor_group_level()},
            prefix="new-group",
        )
        ctx["call_settings_form"] = kwargs.get("call_settings_form") or CallSettingsForm(
            instance=settings,
            event=self.request.event,
        )
        if ctx["active_tab"] == "call":
            # Server-render the saved Call text (per language, matching the
            # preview endpoint) so the preview tab is not blank on load.
            call_text = settings.call_text.data
            if not isinstance(call_text, dict):
                call_text = dict.fromkeys(self.request.event.settings.locales, call_text or "")
            ctx["call_text_previews"] = [
                (locale, rich_text(call_text.get(locale, ""))) for locale in self.request.event.settings.locales
            ]
        ctx["show_add_group_form"] = kwargs.get("show_add_group_form", False)
        ctx["expanded_group_pk"] = kwargs.get("expanded_group_pk")
        return ctx

    SYSTEM_QUESTION_FIELD_LABELS = {
        "company": _("Company name"),
        "job_title": _("Job title"),
        "street": _("Address"),
    }

    def get_data_access_fields(self, settings):
        fields = [
            {
                "value": "attendee_name",
                "label": _("Attendee Name"),
                "checked": settings.is_field_allowed("attendee_name"),
            },
            {
                "value": "attendee_email",
                "label": _("Attendee Email"),
                "checked": settings.is_field_allowed("attendee_email"),
            },
        ]
        event = self.request.event
        for field_id, label in self.SYSTEM_QUESTION_FIELD_LABELS.items():
            if get_system_question_base_state(event, field_id) != STATE_REQUIRED:
                continue
            value = f"system_{field_id}"
            fields.append({"value": value, "label": label, "checked": settings.is_field_allowed(value)})

        required_questions = self.request.event.questions.filter(required=True, active=True).order_by("position", "id")
        for question in required_questions:
            value = f"question_{question.pk}"
            fields.append(
                {
                    "value": value,
                    "label": str(question.question),
                    "checked": settings.is_field_allowed(value),
                }
            )
        return fields

    def get_next_sponsor_group_level(self):
        return get_next_sponsor_group_level(self.request.event)

    def post(self, request, *args, **kwargs):
        settings = ExhibitorSettings.objects.get_or_create(event=self.request.event)[0]
        action = request.POST.get("action", "save_exhibitor_settings")
        active_tab = self.get_active_tab()

        if action == "save_exhibitor_settings":
            settings.allowed_fields = request.POST.getlist("exhibitors_access_voucher")
            settings.exhibitors_access_mail_subject = request.POST.get("exhibitors_access_mail_subject", "")
            settings.exhibitors_access_mail_body = request.POST.get("exhibitors_access_mail_body", "")
            settings.save()
            messages.success(self.request, _("Settings have been saved."))
            return redirect(self.get_settings_url("exhibitors"))

        if action == "save_call_settings":
            form = CallSettingsForm(
                request.POST,
                instance=settings,
                event=request.event,
            )
            if form.is_valid():
                form.save()
                messages.success(self.request, _("Call settings have been saved."))
                return redirect(self.get_settings_url("call"))
            return self.render_to_response(self.get_context_data(call_settings_form=form))

        if action == "regenerate_call_secret":
            settings.regenerate_call_secret()
            messages.success(
                self.request,
                _("A new secret call link has been generated. The old link no longer works."),
            )
            return redirect(self.get_settings_url("call"))

        if action == "add_group":
            form = SponsorGroupForm(
                request.POST,
                event=request.event,
                prefix="new-group",
            )
            if form.is_valid():
                group = form.save(commit=False)
                group.event = request.event
                group.save()
                messages.success(self.request, _("Sponsor group added."))
                return redirect(self.get_settings_url("sponsors"))

            return self.render_to_response(
                self.get_context_data(
                    add_group_form=form,
                    show_add_group_form=True,
                )
            )

        if action == "rename_group":
            group = get_object_or_404(SponsorGroup, pk=request.POST.get("group_id"), event=request.event)
            form = SponsorGroupForm(
                request.POST,
                instance=group,
                event=request.event,
                prefix=f"group-{group.pk}",
            )
            if form.is_valid():
                form.save()
                messages.success(self.request, _("Sponsor group updated."))
                return redirect(self.get_settings_url("sponsors"))

            return self.render_to_response(
                self.get_context_data(
                    edit_group_forms={group.pk: form},
                    expanded_group_pk=group.pk,
                )
            )

        if action == "delete_group":
            group = get_object_or_404(SponsorGroup, pk=request.POST.get("group_id"), event=request.event)
            if group.partners.exists():
                messages.error(
                    self.request,
                    _("This sponsor group cannot be deleted while it is assigned to partners."),
                )
            else:
                group.delete()
                messages.success(self.request, _("Sponsor group deleted."))
            return redirect(self.get_settings_url("sponsors"))

        messages.error(self.request, _("Unknown action."))
        return redirect(self.get_settings_url(active_tab))


class ExhibitorListView(EventPermissionRequiredMixin, ListView):
    model = ExhibitorInfo
    permission = ("can_change_event_settings", "can_view_orders")
    template_name = "exhibitors/exhibitor_info.html"
    context_object_name = "exhibitors"
    partner_type = None

    def get_queryset(self):
        queryset = ExhibitorInfo.objects.filter(event=self.request.event).select_related("sponsor_group")
        if self.partner_type == "sponsor":
            return queryset.filter(is_sponsor=True).order_by("sponsor_position", "name", "pk")
        elif self.partner_type == "exhibitor":
            return queryset.filter(is_exhibitor=True).order_by("exhibitor_position", "name", "pk")
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["partner_type"] = self.partner_type
        if self.partner_type == "sponsor":
            context["sponsor_group_sections"] = self.build_sponsor_group_sections(context["exhibitors"])
        return context

    def build_sponsor_group_sections(self, sponsors):
        groups = list(SponsorGroup.objects.filter(event=self.request.event).order_by("level", "pk"))
        sections = [{"group": group, "partners": []} for group in groups]
        ungrouped = {"group": None, "partners": []}
        section_by_group = {group.pk: section for group, section in zip(groups, sections)}
        for sponsor in sponsors:
            section = section_by_group.get(sponsor.sponsor_group_id, ungrouped)
            section["partners"].append(sponsor)
        return sections + [ungrouped]


class PublicExhibitorListView(ListView):
    model = ExhibitorInfo
    template_name = "exhibitors/public_list.html"
    context_object_name = "exhibitors"

    def get_queryset(self):
        return public_exhibitors_queryset(self.request.event)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["event"] = self.request.event
        context["social_image"] = self.request.event.visible_header_image_url
        add_external_image_csp_sources(
            self.request,
            [
                image_url
                for exhibitor in context["exhibitors"]
                for image_url in (
                    exhibitor.visible_header_image_url,
                    exhibitor.visible_logo_url,
                )
                if image_url
            ],
        )
        return context


class PublicExhibitorDetailView(DetailView):
    model = ExhibitorInfo
    template_name = "exhibitors/public_detail.html"
    context_object_name = "exhibitor"

    def get_queryset(self):
        return public_exhibitors_queryset(self.request.event)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        exhibitors = list(public_exhibitors_queryset(self.request.event))
        context["event"] = self.request.event
        context["social_image"] = self.object.visible_header_image_url or self.object.visible_logo_url
        if len(exhibitors) > 1:
            current_index = next(index for index, exhibitor in enumerate(exhibitors) if exhibitor.pk == self.object.pk)
            context["previous_exhibitor"] = exhibitors[current_index - 1]
            context["next_exhibitor"] = exhibitors[(current_index + 1) % len(exhibitors)]
        else:
            context["previous_exhibitor"] = None
            context["next_exhibitor"] = None

        context["social_links"] = [serialize_social_link(link) for link in self.object.social_links.all()]
        context["extra_links"] = list(self.object.extra_links.all())
        context["video_embed"] = build_exhibitor_video_embed(self.object.video_url or "")
        context["slides_document_url"] = self.object.visible_slides_url

        add_external_image_csp_sources(
            self.request,
            [
                image_url
                for image_url in (
                    self.object.visible_header_image_url,
                    self.object.visible_logo_url,
                )
                if image_url
            ],
        )
        return context


class PublicCallView(PublicCallEnabledMixin, TemplateView):
    template_name = "exhibitors/public_call.html"
    hide_after_deadline = True
    enforce_private = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["event"] = self.request.event
        context["settings"] = self.get_exhibition_settings()
        if self.request.user.is_authenticated:
            context["user_proposals"] = ExhibitionProposal.objects.filter(
                event=self.request.event,
                user=self.request.user,
            )
        return context


class PublicCallSecretView(PublicCallView):
    enforce_private = False

    def grant_secret_access(self, request, secret):
        settings = self.get_exhibition_settings()
        if not settings.call_enabled or not settings.call_private or not secret or secret != settings.call_secret:
            raise Http404()
        request.session[call_access_session_key(request.event)] = secret
        return settings

    def dispatch(self, request, *args, **kwargs):
        self.grant_secret_access(request, kwargs.get("secret"))
        return super().dispatch(request, *args, **kwargs)


class UserProposalListView(PublicCallEnabledMixin, PublicEventLoginRequiredMixin, ListView):
    model = ExhibitionProposal
    template_name = "exhibitors/public_proposal_list.html"
    context_object_name = "proposals"
    enforce_private = True

    def has_private_call_access(self, settings):
        if super().has_private_call_access(settings):
            return True
        user = self.request.user
        if not user.is_authenticated:
            return False
        return ExhibitionProposal.objects.filter(event=self.request.event, user=user).exists()

    def get_queryset(self):
        return ExhibitionProposal.objects.filter(
            event=self.request.event,
            user=self.request.user,
        ).order_by("-updated", "-created")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["settings"] = self.get_exhibition_settings()
        return context


class ProposalLinkFormsetMixin:
    social_formset_prefix = "social_links"
    extra_formset_prefix = "extra_links"

    def get_proposal_field_settings(self):
        settings = ExhibitorSettings.objects.get_or_create(event=self.request.event)[0]
        return settings.normalized_proposal_field_settings

    def proposal_field_is_active(self, key):
        return self.get_proposal_field_settings()[key]["active"]

    def get_formset_instance(self):
        obj = getattr(self, "object", None)
        if obj is not None:
            return obj
        return ExhibitionProposal(event=self.request.event, user=self.request.user)

    def get_social_formset(self):
        return ExhibitionProposalSocialLinkFormSet(
            data=self.request.POST if self.request.method == "POST" else None,
            instance=self.get_formset_instance(),
            prefix=self.social_formset_prefix,
        )

    def get_extra_link_formset(self):
        return ExhibitionProposalExtraLinkFormSet(
            data=self.request.POST if self.request.method == "POST" else None,
            instance=self.get_formset_instance(),
            prefix=self.extra_formset_prefix,
        )

    def post_with_formsets(self):
        form = self.get_form()
        self.social_media_formset = self.get_social_formset() if self.proposal_field_is_active("social_links") else None
        self.extra_links_formset = (
            self.get_extra_link_formset() if self.proposal_field_is_active("extra_links") else None
        )

        if (
            form.is_valid()
            and (self.social_media_formset is None or self.social_media_formset.is_valid())
            and (self.extra_links_formset is None or self.extra_links_formset.is_valid())
        ):
            return self.form_valid(form)
        return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["social_media_formset"] = kwargs.get(
            "social_media_formset",
            getattr(self, "social_media_formset", None) or self.get_social_formset(),
        )
        context["extra_links_formset"] = kwargs.get(
            "extra_links_formset",
            getattr(self, "extra_links_formset", None) or self.get_extra_link_formset(),
        )
        context["social_link_prefixes"] = social_link_prefixes()
        context["settings"] = self.get_exhibition_settings()
        context["show_social_links"] = self.proposal_field_is_active("social_links")
        context["show_extra_links"] = self.proposal_field_is_active("extra_links")
        context.setdefault("can_edit", True)
        return context

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def save_link_formsets(self):
        if self.social_media_formset is not None:
            self.social_media_formset.instance = self.object
            self.social_media_formset.save()
        if self.extra_links_formset is not None:
            self.extra_links_formset.instance = self.object
            self.extra_links_formset.save()


class UserProposalCreateView(
    ProposalLinkFormsetMixin,
    PublicCallEnabledMixin,
    PublicEventLoginRequiredMixin,
    CreateView,
):
    model = ExhibitionProposal
    form_class = ExhibitionProposalForm
    template_name = "exhibitors/public_proposal_form.html"

    def dispatch(self, request, *args, **kwargs):
        settings = ExhibitorSettings.objects.get_or_create(event=request.event)[0]
        if not settings.call_enabled:
            raise Http404()
        if settings.call_private and not self.has_private_call_access(settings):
            raise Http404()
        if not settings.call_is_open:
            if settings.call_hide_after_deadline:
                raise Http404()
            messages.error(request, _("The call for exhibitors is closed."))
            return redirect("plugins:exhibition:public_call", **event_kwargs(request.event))
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        kwargs["draft_save"] = self.request.POST.get("action") == "draft"
        return kwargs

    def post(self, request, *args, **kwargs):
        self.object = None
        return self.post_with_formsets()

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event
        form.instance.user = self.request.user
        if self.request.POST.get("action") == "draft":
            form.instance.state = ExhibitionProposalState.DRAFT
            form.instance.submitted = None
        else:
            form.instance.state = ExhibitionProposalState.SUBMITTED
            form.instance.submitted = timezone.now()
        response = super().form_valid(form)
        self.save_link_formsets()
        if form.instance.state == ExhibitionProposalState.SUBMITTED:
            send_proposal_confirmation(self.request.event, self.object, self.request.user)
        messages.success(self.request, _("Your request has been saved."))
        return response

    def get_success_url(self):
        return reverse(
            "plugins:exhibition:proposal.user_list",
            kwargs=event_kwargs(self.request.event),
        )


class UserProposalEditView(
    ProposalLinkFormsetMixin,
    PublicCallEnabledMixin,
    PublicEventLoginRequiredMixin,
    UpdateView,
):
    model = ExhibitionProposal
    form_class = ExhibitionProposalForm
    template_name = "exhibitors/public_proposal_form.html"
    slug_field = "code"
    slug_url_kwarg = "code"

    def get_queryset(self):
        return ExhibitionProposal.objects.filter(
            event=self.request.event,
            user=self.request.user,
        ).prefetch_related("answers", "answers__options")

    def can_edit(self):
        settings = self.get_exhibition_settings()
        return self.object.editable and settings.call_is_open

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        kwargs["read_only"] = not self.can_edit()
        kwargs["draft_save"] = self.request.POST.get("action") == "draft"
        return kwargs

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.can_edit():
            messages.error(request, _("This request can no longer be edited."))
            return redirect(self.get_success_url())
        return self.post_with_formsets()

    @transaction.atomic
    def form_valid(self, form):
        previous_state = self.object.state
        if self.request.POST.get("action") == "draft":
            form.instance.state = ExhibitionProposalState.DRAFT
            form.instance.submitted = None
        else:
            form.instance.state = ExhibitionProposalState.SUBMITTED
            form.instance.submitted = form.instance.submitted or timezone.now()
        response = super().form_valid(form)
        self.save_link_formsets()
        if (
            form.instance.state == ExhibitionProposalState.SUBMITTED
            and previous_state != ExhibitionProposalState.SUBMITTED
        ):
            send_proposal_confirmation(self.request.event, self.object, self.request.user)
        messages.success(self.request, _("Your request has been saved."))
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_edit"] = self.can_edit()
        return context

    def get_success_url(self):
        return reverse(
            "plugins:exhibition:proposal.user_list",
            kwargs=event_kwargs(self.request.event),
        )


class UserProposalWithdrawView(PublicCallEnabledMixin, PublicEventLoginRequiredMixin, DetailView):
    model = ExhibitionProposal
    template_name = "exhibitors/public_proposal_withdraw.html"
    context_object_name = "proposal"
    slug_field = "code"
    slug_url_kwarg = "code"

    def get_queryset(self):
        return ExhibitionProposal.objects.filter(
            event=self.request.event,
            user=self.request.user,
        )

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.can_be_withdrawn:
            messages.error(request, _("This proposal can no longer be withdrawn."))
            return redirect(self.get_success_url())
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.can_be_withdrawn:
            self.object.withdraw()
            messages.success(request, _("Your proposal has been withdrawn."))
        else:
            messages.error(request, _("This proposal can no longer be withdrawn."))
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse(
            "plugins:exhibition:proposal.user_list",
            kwargs=event_kwargs(self.request.event),
        )


class ExhibitorLinkFormsetMixin:
    social_formset_prefix = "social_links"
    extra_formset_prefix = "extra_links"

    def get_proposal_field_settings(self):
        settings = ExhibitorSettings.objects.get_or_create(event=self.request.event)[0]
        return settings.normalized_proposal_field_settings

    def proposal_field_is_active(self, key):
        return self.get_proposal_field_settings()[key]["active"]

    def get_formset_instance(self):
        obj = getattr(self, "object", None)
        return obj if obj is not None else ExhibitorInfo(event=self.request.event)

    def get_social_formset(self):
        return ExhibitorSocialLinkFormSet(
            data=self.request.POST if self.request.method == "POST" else None,
            instance=self.get_formset_instance(),
            prefix=self.social_formset_prefix,
        )

    def get_extra_link_formset(self):
        return ExhibitorExtraLinkFormSet(
            data=self.request.POST if self.request.method == "POST" else None,
            instance=self.get_formset_instance(),
            prefix=self.extra_formset_prefix,
        )

    def post_with_formsets(self):
        form = self.get_form()
        self.social_media_formset = self.get_social_formset() if self.proposal_field_is_active("social_links") else None
        self.extra_links_formset = (
            self.get_extra_link_formset() if self.proposal_field_is_active("extra_links") else None
        )

        if (
            form.is_valid()
            and (self.social_media_formset is None or self.social_media_formset.is_valid())
            and (self.extra_links_formset is None or self.extra_links_formset.is_valid())
        ):
            return self.form_valid(form)
        return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        show_social_links = self.proposal_field_is_active("social_links")
        show_extra_links = self.proposal_field_is_active("extra_links")
        context["social_media_formset"] = kwargs.get(
            "social_media_formset",
            getattr(self, "social_media_formset", self.get_social_formset() if show_social_links else None),
        )
        context["extra_links_formset"] = kwargs.get(
            "extra_links_formset",
            getattr(self, "extra_links_formset", self.get_extra_link_formset() if show_extra_links else None),
        )
        context["social_link_prefixes"] = social_link_prefixes()
        return context

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def save_link_formsets(self):
        for formset in (self.social_media_formset, self.extra_links_formset):
            if formset is None:
                continue
            formset.instance = self.object
            formset.save()


class SponsorGroupFrontPageToggleView(EventPermissionRequiredMixin, View):
    permission = "can_change_settings"

    def post(self, request, *args, **kwargs):
        group = get_object_or_404(SponsorGroup, pk=kwargs["pk"], event=request.event)
        group.show_on_front_page = not group.show_on_front_page
        group.save(update_fields=["show_on_front_page"])
        return JsonResponse({"show_on_front_page": group.show_on_front_page})


class SponsorGroupReorderView(EventPermissionRequiredMixin, View):
    permission = "can_change_settings"

    def post(self, request, *args, **kwargs):
        try:
            group_ids = json.loads(request.body.decode("utf-8")).get("group_ids", [])
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"detail": _("Invalid request body.")}, status=400)

        if not isinstance(group_ids, list):
            return JsonResponse({"detail": _("Invalid sponsor group IDs.")}, status=400)

        try:
            group_ids = [int(group_id) for group_id in group_ids]
        except (TypeError, ValueError):
            return JsonResponse({"detail": _("Invalid sponsor group IDs.")}, status=400)

        if len(group_ids) != len(set(group_ids)):
            return JsonResponse(
                {"detail": _("Sponsor group IDs must be unique.")},
                status=400,
            )

        groups = list(SponsorGroup.objects.filter(event=request.event).order_by("level", "pk"))
        known_group_ids = [group.pk for group in groups]
        if len(group_ids) != len(known_group_ids) or set(group_ids) != set(known_group_ids):
            return JsonResponse(
                {"detail": _("Reorder request must include each sponsor group exactly once.")},
                status=400,
            )

        group_lookup = {group.pk: group for group in groups}
        ordered_groups = [group_lookup[group_id] for group_id in group_ids]

        with transaction.atomic():
            for index, group in enumerate(ordered_groups, start=1):
                group.level = index
            SponsorGroup.objects.bulk_update(ordered_groups, ["level"])

        return JsonResponse({"levels": [{"id": group.pk, "level": group.level} for group in ordered_groups]})


class PartnerReorderMixin(EventPermissionRequiredMixin, View):
    permission = "can_change_event_settings"
    position_field = None

    def get_scope_queryset(self, request):
        raise NotImplementedError

    def post(self, request, *args, **kwargs):
        order_param = (request.POST.get("order") or "").strip()
        if not order_param:
            return HttpResponse(status=400)

        try:
            ids = [int(token) for token in order_param.split(",") if token.strip()]
        except ValueError:
            return HttpResponse(status=400)
        if not ids or len(ids) != len(set(ids)):
            return HttpResponse(status=400)

        partners = {partner.pk: partner for partner in self.get_scope_queryset(request)}
        if set(ids) != set(partners):
            return HttpResponse(status=400)

        ordered = [partners[value] for value in ids]
        with transaction.atomic():
            for index, partner in enumerate(ordered):
                setattr(partner, self.position_field, index)
            ExhibitorInfo.objects.bulk_update(ordered, [self.position_field])

        return HttpResponse(status=204)


class ExhibitorReorderView(PartnerReorderMixin):
    position_field = "exhibitor_position"

    def get_scope_queryset(self, request):
        return ExhibitorInfo.objects.filter(event=request.event, is_exhibitor=True)


class SponsorReorderView(PartnerReorderMixin):
    position_field = "sponsor_position"

    def get_scope_queryset(self, request):
        group_id = request.GET.get("group_id")
        queryset = ExhibitorInfo.objects.filter(event=request.event, is_sponsor=True)
        if group_id in (None, "", "none"):
            return queryset.filter(sponsor_group__isnull=True)
        try:
            group_id = int(group_id)
        except (TypeError, ValueError):
            return queryset.none()
        return queryset.filter(sponsor_group_id=group_id)


class CallTextPreviewView(EventPermissionRequiredMixin, View):
    """Render draft Call text with the same Markdown conversion as the public call page."""

    permission = "can_change_settings"

    def post(self, request, *args, **kwargs):
        widget = CallSettingsForm(event=request.event).fields["call_text"].widget
        # The i18n widget returns values as a list indexed by global LANGUAGES order.
        values = widget.value_from_datadict(request.POST, request.FILES, "call_text")
        if not isinstance(values, (list, tuple)):
            values = [values]
        event_locales = set(request.event.settings.locales)
        msgs = {}
        for index, (code, _name) in enumerate(django_settings.LANGUAGES):
            if code in event_locales and index < len(values):
                text = values[index]
                msgs[code] = str(rich_text(text)) if text else ""
        return JsonResponse({"msgs": msgs})


class ProposalListView(EventPermissionRequiredMixin, ListView):
    model = ExhibitionProposal
    permission = ("can_change_event_settings", "can_change_exhibition_proposals", "is_exhibition_reviewer")
    template_name = "exhibitors/proposal_list.html"
    context_object_name = "proposals"

    def get_queryset(self):
        return (
            ExhibitionProposal.objects.filter(event=self.request.event)
            .select_related("user", "sponsor_group", "approved_exhibitor")
            .order_by("-updated", "-created")
        )

    def can_manage(self):
        return self.request.user.has_event_permission(
            self.request.event.organizer,
            self.request.event,
            ("can_change_event_settings", "can_change_exhibition_proposals"),
            request=self.request,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["hide_applicant_emails"] = should_hide_applicant_emails(
            self.request.user, self.request.event, request=self.request
        )
        context["can_manage"] = self.can_manage()
        context["actionable_state"] = ExhibitionProposalState.SUBMITTED
        return context


class ProposalDetailView(EventPermissionRequiredMixin, UpdateView):
    model = ExhibitionProposal
    permission = ("can_change_event_settings", "can_change_exhibition_proposals", "is_exhibition_reviewer")
    template_name = "exhibitors/proposal_detail.html"
    context_object_name = "proposal"
    slug_field = "code"
    slug_url_kwarg = "code"

    def can_manage(self):
        return self.request.user.has_event_permission(
            self.request.event.organizer,
            self.request.event,
            ("can_change_event_settings", "can_change_exhibition_proposals"),
            request=self.request,
        )

    def can_edit_exhibitor(self):
        return self.request.user.has_event_permission(
            self.request.event.organizer,
            self.request.event,
            "can_change_event_settings",
            request=self.request,
        )

    def can_review(self):
        return self.can_manage() and self.object.state == ExhibitionProposalState.SUBMITTED

    def get_form_class(self):
        if self.can_review():
            return ExhibitionProposalReviewForm
        return ExhibitionProposalReviewNotesForm

    def get_queryset(self):
        return (
            ExhibitionProposal.objects.filter(event=self.request.event)
            .select_related("user", "sponsor_group", "approved_exhibitor")
            .prefetch_related(
                "answers",
                "answers__options",
                "answers__question",
                "social_links",
                "extra_links",
            )
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["answers"] = self.object.answers.select_related("question").prefetch_related("options")
        context["can_manage"] = self.can_manage()
        context["can_review"] = self.can_review()
        context["can_edit_exhibitor"] = self.can_edit_exhibitor()
        context["hide_applicant_emails"] = should_hide_applicant_emails(
            self.request.user, self.request.event, request=self.request
        )
        return context

    @transaction.atomic
    def form_valid(self, form):
        self.object = form.save()
        action = self.request.POST.get("action", "save")
        if action in ("approve", "reject"):
            if not self.can_manage():
                raise PermissionDenied()
            if self.object.state != ExhibitionProposalState.SUBMITTED:
                messages.error(self.request, _("This proposal can no longer be changed."))
                return redirect(self.get_success_url())
        if action == "approve":
            exhibitor = self.object.approve(requestor=self.request.user)
            messages.success(
                self.request,
                _("Request approved and partner profile created. An acceptance email was placed in the outbox."),
            )
            if self.can_edit_exhibitor():
                return redirect(
                    "plugins:exhibition:edit",
                    **event_kwargs(self.request.event),
                    pk=exhibitor.pk,
                )
            return redirect(self.get_success_url())
        if action == "reject":
            if self.object.approved_exhibitor_id:
                messages.error(
                    self.request,
                    _("This request has already been approved and cannot be rejected."),
                )
            else:
                self.object.reject(requestor=self.request.user)
                messages.success(
                    self.request,
                    _("Request rejected. A rejection email was placed in the outbox."),
                )
            return redirect(self.get_success_url())

        messages.success(self.request, _("Review details saved."))
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse(
            "plugins:exhibition:proposal.detail",
            kwargs={**event_kwargs(self.request.event), "code": self.object.code},
        )


class ProposalActionView(EventPermissionRequiredMixin, View):
    permission = ("can_change_event_settings", "can_change_exhibition_proposals")
    valid_actions = {"approve", "reject", "withdraw"}

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        codes = request.POST.getlist("proposal")
        if action not in self.valid_actions or not codes:
            return self.respond(request, False, _("No valid action was selected."), [], 0)

        proposals = ExhibitionProposal.objects.filter(event=request.event, code__in=codes).select_related(
            "approved_exhibitor"
        )
        results = []
        skipped = 0
        with transaction.atomic():
            for proposal in proposals:
                if proposal.state != ExhibitionProposalState.SUBMITTED:
                    skipped += 1
                    continue
                self.apply_action(proposal, action)
                results.append(
                    {
                        "code": proposal.code,
                        "state": proposal.state,
                        "state_display": proposal.get_state_display(),
                    }
                )
        return self.respond(request, True, self.build_message(action, len(results), skipped), results, skipped)

    def apply_action(self, proposal, action):
        if action == "approve":
            proposal.approve(requestor=self.request.user)
        elif action == "reject":
            proposal.reject(requestor=self.request.user)
        elif action == "withdraw":
            proposal.state = ExhibitionProposalState.WITHDRAWN
            proposal.save(update_fields=["state", "updated"])

    def build_message(self, action, count, skipped):
        if count:
            templates = {
                "approve": ngettext("%(count)d proposal was approved.", "%(count)d proposals were approved.", count),
                "reject": ngettext("%(count)d proposal was rejected.", "%(count)d proposals were rejected.", count),
                "withdraw": ngettext("%(count)d proposal was withdrawn.", "%(count)d proposals were withdrawn.", count),
            }
            message = templates[action] % {"count": count}
        else:
            message = _("No proposals were updated.")
        if skipped:
            skipped_message = ngettext(
                "%(skipped)d was skipped because it was already processed.",
                "%(skipped)d were skipped because they were already processed.",
                skipped,
            ) % {"skipped": skipped}
            message = f"{message} {skipped_message}"
        return message

    def respond(self, request, ok, message, results, skipped):
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {"ok": ok, "message": str(message), "results": results, "skipped": skipped},
                status=200 if ok else 400,
            )
        if ok:
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect("plugins:exhibition:proposal.list", **event_kwargs(request.event))


class ExhibitionQuestionListView(EventPermissionRequiredMixin, ListView):
    model = ExhibitionQuestion
    permission = "can_change_settings"
    template_name = "exhibitors/call_questions.html"
    context_object_name = "questions"

    def get_queryset(self):
        return ExhibitionQuestion.objects.filter(event=self.request.event).annotate(answer_count=Count("answers"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        settings = ExhibitorSettings.objects.get_or_create(event=self.request.event)[0]
        field_settings = settings.normalized_proposal_field_settings
        answer_counts = self.get_default_field_answer_counts()
        field_definitions = {field["key"]: field for field in PROPOSAL_DEFAULT_FIELDS}
        formset_keys = set(PROPOSAL_FORMSET_FIELD_KEYS)

        orderable_rows = []
        for key in PROPOSAL_DEFAULT_FIELD_KEYS:
            if key in formset_keys:
                continue
            definition = field_definitions[key]
            orderable_rows.append(
                {
                    "sort_position": field_settings[key]["position"],
                    "sort_kind": 0,
                    "dragsort_id": key,
                    "input_prefix": key,
                    "label": definition["label"],
                    "active": field_settings[key]["active"],
                    "required": field_settings[key]["required"],
                    "supports_required": definition.get("supports_required", True),
                    "active_locked": definition.get("active_locked", False),
                    "required_locked": definition.get("required_locked", False),
                    "answer_count": answer_counts.get(key, 0),
                    "orderable": True,
                    "is_custom": False,
                }
            )
        for question in context["questions"]:
            orderable_rows.append(
                {
                    "sort_position": question.position,
                    "sort_kind": 1,
                    "dragsort_id": question.pk,
                    "input_prefix": f"question_{question.pk}",
                    "label": question.localized_question,
                    "active": question.active,
                    "required": question.required,
                    "supports_required": True,
                    "active_locked": False,
                    "required_locked": False,
                    "answer_count": question.answer_count,
                    "orderable": True,
                    "is_custom": True,
                    "pk": question.pk,
                }
            )
        orderable_rows.sort(key=lambda row: (row["sort_position"], row["sort_kind"]))

        formset_rows = [
            {
                "dragsort_id": key,
                "input_prefix": key,
                "label": field_definitions[key]["label"],
                "active": field_settings[key]["active"],
                "required": field_settings[key]["required"],
                "supports_required": field_definitions[key].get("supports_required", True),
                "active_locked": field_definitions[key].get("active_locked", False),
                "required_locked": field_definitions[key].get("required_locked", False),
                "answer_count": answer_counts.get(key, 0),
                "orderable": False,
                "is_custom": False,
            }
            for key in PROPOSAL_FORMSET_FIELD_KEYS
        ]
        context["proposal_fields"] = orderable_rows + formset_rows
        return context

    def get_default_field_answer_counts(self):
        proposals = ExhibitionProposal.objects.filter(event=self.request.event).exclude(
            state=ExhibitionProposalState.DRAFT
        )
        file_has_value = {
            "slides": (Q(slides__isnull=False) & ~Q(slides="")) | (Q(slides_url__isnull=False) & ~Q(slides_url="")),
            "logo": (Q(logo__isnull=False) & ~Q(logo="")) | (Q(logo_url__isnull=False) & ~Q(logo_url="")),
            "header_image": (Q(header_image__isnull=False) & ~Q(header_image=""))
            | (Q(header_image_url__isnull=False) & ~Q(header_image_url="")),
        }
        text_fields = (
            "description",
            "email",
            "url",
            "contact_url",
            "video_url",
            "booth_name",
            "notes",
        )
        counts = {
            "name": proposals.count(),
            "social_links": proposals.filter(social_links__isnull=False).distinct().count(),
            "extra_links": proposals.filter(extra_links__isnull=False).distinct().count(),
        }
        counts.update({key: proposals.filter(condition).count() for key, condition in file_has_value.items()})
        counts.update(
            {
                field: proposals.exclude(**{f"{field}__isnull": True}).exclude(**{field: ""}).count()
                for field in text_fields
            }
        )
        return counts

    def post(self, request, *args, **kwargs):
        settings = ExhibitorSettings.objects.get_or_create(event=request.event)[0]

        order_param = request.POST.get("order")
        if order_param:
            self.save_field_order(settings, order_param)
            return HttpResponse(status=204)

        proposal_field_settings = settings.normalized_proposal_field_settings

        for field in PROPOSAL_DEFAULT_FIELDS:
            key = field["key"]
            is_active = field.get("active_locked") or request.POST.get(f"{key}_active") == "on"
            proposal_field_settings[key]["active"] = is_active
            proposal_field_settings[key]["required"] = is_active and (
                field.get("required_locked")
                or (field.get("supports_required", True) and request.POST.get(f"{key}_required") == "on")
            )
            if field.get("supports_required") is False:
                proposal_field_settings[key]["required"] = False

        settings.proposal_field_settings = proposal_field_settings
        settings.save(update_fields=["proposal_field_settings"])

        questions = list(ExhibitionQuestion.objects.filter(event=request.event))
        for question in questions:
            question.active = request.POST.get(f"question_{question.pk}_active") == "on"
            question.required = request.POST.get(f"question_{question.pk}_required") == "on"
        if questions:
            ExhibitionQuestion.objects.bulk_update(questions, ["active", "required"])

        messages.success(request, _("Exhibitor form settings have been saved."))
        return redirect("plugins:exhibition:call.questions", **event_kwargs(request.event))

    def save_field_order(self, settings, order_str):
        proposal_field_settings = settings.normalized_proposal_field_settings
        orderable_keys = [key for key in PROPOSAL_DEFAULT_FIELD_KEYS if key not in PROPOSAL_FORMSET_FIELD_KEYS]
        orderable_key_set = set(orderable_keys)
        questions = {question.pk: question for question in ExhibitionQuestion.objects.filter(event=settings.event)}
        seen_keys = set()
        seen_question_pks = set()
        reordered_questions = []
        position = 0
        for token in (raw_token.strip() for raw_token in order_str.split(",")):
            if token in orderable_key_set and token not in seen_keys:
                seen_keys.add(token)
                proposal_field_settings[token]["position"] = position
                position += 1
            elif token.isdigit() and int(token) in questions and int(token) not in seen_question_pks:
                question = questions[int(token)]
                question.position = position
                seen_question_pks.add(question.pk)
                reordered_questions.append(question)
                position += 1
        for key in orderable_keys:
            if key not in seen_keys:
                proposal_field_settings[key]["position"] = position
                position += 1
        remaining_questions = sorted(
            (question for pk, question in questions.items() if pk not in seen_question_pks),
            key=lambda question: (question.position, question.pk),
        )
        for question in remaining_questions:
            question.position = position
            reordered_questions.append(question)
            position += 1
        for key in PROPOSAL_FORMSET_FIELD_KEYS:
            proposal_field_settings[key]["position"] = position
            position += 1
        settings.proposal_field_settings = proposal_field_settings
        settings.save(update_fields=["proposal_field_settings"])
        if reordered_questions:
            ExhibitionQuestion.objects.bulk_update(reordered_questions, ["position"])


class ExhibitionQuestionCreateView(EventPermissionRequiredMixin, CreateView):
    model = ExhibitionQuestion
    form_class = ExhibitionQuestionForm
    permission = "can_change_settings"
    template_name = "exhibitors/call_question_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        return kwargs

    def get_success_url(self):
        return reverse(
            "plugins:exhibition:call.questions",
            kwargs=event_kwargs(self.request.event),
        )


class ExhibitionQuestionEditView(EventPermissionRequiredMixin, UpdateView):
    model = ExhibitionQuestion
    form_class = ExhibitionQuestionForm
    permission = "can_change_settings"
    template_name = "exhibitors/call_question_form.html"

    def get_queryset(self):
        return ExhibitionQuestion.objects.filter(event=self.request.event)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        return kwargs

    def get_success_url(self):
        return reverse(
            "plugins:exhibition:call.questions",
            kwargs=event_kwargs(self.request.event),
        )


class ExhibitionQuestionDeleteView(EventPermissionRequiredMixin, DeleteView):
    model = ExhibitionQuestion
    permission = "can_change_settings"
    template_name = "exhibitors/call_question_delete.html"

    def get_queryset(self):
        return ExhibitionQuestion.objects.filter(event=self.request.event)

    def get_success_url(self):
        return reverse(
            "plugins:exhibition:call.questions",
            kwargs=event_kwargs(self.request.event),
        )


class ExhibitorCreateView(ExhibitorLinkFormsetMixin, EventPermissionRequiredMixin, CreateView):
    model = ExhibitorInfo
    form_class = ExhibitorInfoForm
    template_name = "exhibitors/add.html"
    permission = "can_change_event_settings"
    partner_type = None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["partner_type"] = self.partner_type
        return kwargs

    def post(self, request, *args, **kwargs):
        self.object = None
        return self.post_with_formsets()

    @transaction.atomic
    def form_valid(self, form):
        form.instance.event = self.request.event

        # Only generate booth_id for exhibitors if none was provided.
        if form.cleaned_data.get("is_exhibitor", True) and not form.cleaned_data.get("booth_id"):
            form.instance.booth_id = generate_booth_id(event=self.request.event)

        response = super().form_valid(form)
        self.save_link_formsets()
        if form.instance.lead_scanning_enabled and queue_exhibitor_access_mail(
            self.request.event, self.object, self.request.user
        ):
            messages.info(self.request, _("An access-credentials email was placed in the outbox."))
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action"] = "create"
        context["partner_type"] = self.partner_type
        context["page_title"] = {
            "sponsor": _("Add a Sponsor"),
            "exhibitor": _("Add an Exhibitor"),
        }.get(self.partner_type, _("Add an Exhibitor or Sponsor"))
        return context

    def get_success_url(self):
        return partner_list_url(self.request.event, self.partner_type)


class ExhibitorEditView(ExhibitorLinkFormsetMixin, EventPermissionRequiredMixin, UpdateView):
    model = ExhibitorInfo
    form_class = ExhibitorInfoForm
    template_name = "exhibitors/add.html"
    permission = "can_change_event_settings"

    def get_queryset(self):
        return ExhibitorInfo.objects.filter(event=self.request.event)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self.post_with_formsets()

    def get_initial(self):
        initial = super().get_initial()
        obj = self.get_object()
        initial["lead_scanning_enabled"] = obj.lead_scanning_enabled
        return initial

    @transaction.atomic
    def form_valid(self, form):
        was_lead_scanning_enabled = (
            ExhibitorInfo.objects.filter(pk=self.object.pk).values_list("lead_scanning_enabled", flat=True).first()
        )

        # Generate booth_id only for exhibitors if none exists.
        if (
            form.cleaned_data.get("is_exhibitor", True)
            and not form.cleaned_data.get("booth_id")
            and not form.instance.booth_id
        ):
            form.instance.booth_id = generate_booth_id(event=self.request.event)

        response = super().form_valid(form)
        self.save_link_formsets()
        if (
            form.instance.lead_scanning_enabled
            and not was_lead_scanning_enabled
            and queue_exhibitor_access_mail(self.request.event, self.object, self.request.user)
        ):
            messages.info(self.request, _("An access-credentials email was placed in the outbox."))
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["action"] = "edit"
        context["page_title"] = {
            "sponsor": _("Edit Sponsor"),
            "exhibitor": _("Edit Exhibitor"),
            "both": _("Edit Exhibitor & Sponsor"),
        }.get(partner_type_of(self.object), _("Edit Exhibitor or Sponsor"))
        return context

    def get_success_url(self):
        # Return to the list the partner was edited from; fall back to its type.
        partner_type = self.request.GET.get("type")
        if partner_type not in ("sponsor", "exhibitor"):
            partner_type = "sponsor" if self.object.is_sponsor and not self.object.is_exhibitor else "exhibitor"
        return partner_list_url(self.request.event, partner_type)


class ExhibitorDeleteView(EventPermissionRequiredMixin, DeleteView):
    model = ExhibitorInfo
    template_name = "exhibitors/delete.html"
    permission = ("can_change_event_settings",)

    def get_queryset(self):
        return ExhibitorInfo.objects.filter(event=self.request.event)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = {
            "sponsor": _("Delete Sponsor"),
            "exhibitor": _("Delete Exhibitor"),
            "both": _("Delete Exhibitor & Sponsor"),
        }.get(partner_type_of(self.object), _("Delete Exhibitor or Sponsor"))
        return context

    def get_success_url(self) -> str:
        return reverse(
            "plugins:exhibition:info",
            kwargs={
                "organizer": self.request.event.organizer.slug,
                "event": self.request.event.slug,
            },
        )


class ExhibitorCopyKeyView(EventPermissionRequiredMixin, View):
    permission = ("can_change_event_settings",)

    def get(self, request, *args, **kwargs):
        exhibitor = get_object_or_404(ExhibitorInfo, pk=kwargs["pk"], event=request.event)
        response = JsonResponse({"key": exhibitor.key})
        response["Cache-Control"] = "no-store"
        return response


EMAIL_MANAGE_PERMISSION = (
    "can_change_event_settings",
    "can_change_exhibition_proposals",
    "is_exhibition_reviewer",
)


class EmailComposeView(EventPermissionRequiredMixin, FormView):
    """Compose a broadcast email to a filtered group of applicants."""

    permission = EMAIL_MANAGE_PERMISSION
    template_name = "exhibitors/email_compose.html"
    form_class = ExhibitionComposeForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["email_placeholders"] = mail_helpers.PLACEHOLDER_DOCS
        return context

    def form_valid(self, form):
        from .tasks import send_scheduled_email

        event = self.request.event
        scheduled_at = form.cleaned_data.get("scheduled_at")
        send_now = "_send" in self.request.POST and not scheduled_at

        recipients = mail_helpers.compose_recipients(
            event,
            states=form.cleaned_data["states"],
            partner_type=form.cleaned_data["partner_type"],
            sponsor_group=form.cleaned_data["sponsor_group"],
        )
        created = mail_helpers.queue_compose_emails(
            event,
            recipients,
            form.cleaned_data["subject"],
            form.cleaned_data["body"],
            scheduled_at=scheduled_at,
            send_now=send_now,
            requestor=self.request.user,
        )
        if not created:
            messages.warning(self.request, _("No applicants matched the selected filters."))
            return self.form_invalid(form)

        if scheduled_at:
            for queued in created:
                send_scheduled_email.apply_async(args=[event.pk, queued.pk], eta=scheduled_at)
            messages.success(
                self.request,
                _("%(count)d emails have been scheduled.") % {"count": len(created)},
            )
            return redirect("plugins:exhibition:email.outbox", **event_kwargs(event))
        if send_now:
            messages.success(self.request, _("%(count)d emails have been sent.") % {"count": len(created)})
            return redirect("plugins:exhibition:email.sent", **event_kwargs(event))
        messages.success(
            self.request,
            _("%(count)d emails have been placed in the outbox.") % {"count": len(created)},
        )
        return redirect("plugins:exhibition:email.outbox", **event_kwargs(event))


def group_email_entries(emails):
    """Collapse rows that share a compose batch into one entry per message."""
    entries = []
    by_batch = {}
    for email in emails:
        if email.batch is None:
            entries.append(
                {
                    "pk": email.pk,
                    "subject": email.subject,
                    "recipients": [email.to_email],
                    "created": email.created,
                    "sent_at": email.sent_at,
                    "scheduled_at": email.scheduled_at,
                    "is_batch": False,
                }
            )
            continue
        key = str(email.batch)
        entry = by_batch.get(key)
        if entry is None:
            entry = {
                "pk": email.pk,
                "subject": email.subject,
                "recipients": [],
                "created": email.created,
                "sent_at": email.sent_at,
                "scheduled_at": email.scheduled_at,
                "is_batch": True,
            }
            by_batch[key] = entry
            entries.append(entry)
        entry["recipients"].append(email.to_email)
    return entries


class EmailOutboxListView(EventPermissionRequiredMixin, ListView):
    """Unsent queued emails awaiting organiser review."""

    model = ExhibitionEmailQueue
    permission = EMAIL_MANAGE_PERMISSION
    template_name = "exhibitors/email_outbox.html"
    context_object_name = "emails"

    def get_queryset(self):
        return ExhibitionEmailQueue.objects.filter(event=self.request.event, sent_at__isnull=True).order_by("-created")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["entries"] = group_email_entries(context["emails"])
        return context


class EmailSentListView(EventPermissionRequiredMixin, ListView):
    """Read-only list of already-sent emails."""

    model = ExhibitionEmailQueue
    permission = EMAIL_MANAGE_PERMISSION
    template_name = "exhibitors/email_sent.html"
    context_object_name = "emails"

    def get_queryset(self):
        return ExhibitionEmailQueue.objects.filter(event=self.request.event, sent_at__isnull=False).order_by("-sent_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["entries"] = group_email_entries(context["emails"])
        return context


class EmailEditView(EventPermissionRequiredMixin, UpdateView):
    """Preview and edit a queued (unsent) email before sending."""

    model = ExhibitionEmailQueue
    form_class = ExhibitionEmailQueueForm
    permission = EMAIL_MANAGE_PERMISSION
    template_name = "exhibitors/email_edit.html"
    context_object_name = "email"

    def get_queryset(self):
        return ExhibitionEmailQueue.objects.filter(event=self.request.event, sent_at__isnull=True)

    def batch_queryset(self):
        return ExhibitionEmailQueue.objects.filter(
            event=self.request.event, batch=self.object.batch, sent_at__isnull=True
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.object.batch:
            context["recipients"] = list(self.batch_queryset().values_list("to_email", flat=True))
        else:
            context["recipients"] = [self.object.to_email]
        return context

    def form_valid(self, form):
        self.object = form.save(commit=False)
        subject = form.cleaned_data["subject"]
        body = form.cleaned_data["body"]

        if self.object.batch:
            rows = list(self.batch_queryset())
            self.batch_queryset().update(subject=subject, body=body)
            if "_send" in self.request.POST:
                for row in rows:
                    row.subject = subject
                    row.body = body
                    row.send(requestor=self.request.user)
                messages.success(self.request, _("The emails have been saved and sent."))
            else:
                messages.success(self.request, _("The emails have been saved."))
            return redirect(self.get_success_url())

        self.object.save()
        if "_send" in self.request.POST:
            self.object.send(requestor=self.request.user)
            messages.success(self.request, _("The email has been saved and sent."))
        else:
            messages.success(self.request, _("The email has been saved."))
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("plugins:exhibition:email.outbox", kwargs=event_kwargs(self.request.event))


class EmailSendView(EventPermissionRequiredMixin, View):
    """Send a queued email (or the whole batch it belongs to)."""

    permission = EMAIL_MANAGE_PERMISSION

    def post(self, request, *args, **kwargs):
        email = get_object_or_404(ExhibitionEmailQueue, pk=kwargs["pk"], event=request.event, sent_at__isnull=True)
        if email.batch:
            rows = ExhibitionEmailQueue.objects.filter(event=request.event, batch=email.batch, sent_at__isnull=True)
        else:
            rows = [email]
        count = 0
        for row in rows:
            row.send(requestor=request.user)
            count += 1
        messages.success(
            request,
            ngettext("%(count)d email has been sent.", "%(count)d emails have been sent.", count) % {"count": count},
        )
        return redirect("plugins:exhibition:email.outbox", **event_kwargs(request.event))


class EmailDeleteView(EventPermissionRequiredMixin, DeleteView):
    """Discard a queued email (or the whole batch it belongs to)."""

    model = ExhibitionEmailQueue
    permission = EMAIL_MANAGE_PERMISSION
    template_name = "exhibitors/email_delete.html"
    context_object_name = "email"

    def get_queryset(self):
        return ExhibitionEmailQueue.objects.filter(event=self.request.event, sent_at__isnull=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.object.batch:
            context["recipients"] = list(
                self.get_queryset().filter(batch=self.object.batch).values_list("to_email", flat=True)
            )
        else:
            context["recipients"] = [self.object.to_email]
        return context

    def form_valid(self, form):
        self.object = self.get_object()
        success_url = self.get_success_url()
        if self.object.batch:
            self.get_queryset().filter(batch=self.object.batch).delete()
        else:
            self.object.delete()
        return redirect(success_url)

    def get_success_url(self):
        messages.success(self.request, _("The email has been discarded."))
        return reverse("plugins:exhibition:email.outbox", kwargs=event_kwargs(self.request.event))


class EmailTemplatesView(EventPermissionRequiredMixin, TemplateView):
    """Edit the lifecycle email templates."""

    permission = "can_change_event_settings"
    template_name = "exhibitors/email_templates.html"

    def get_form(self, data=None):
        return ExhibitionMailTemplatesForm(data=data, obj=self.request.event)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = kwargs.get("form") or self.get_form()
        context["form"] = form
        context["template_panels"] = [
            {
                "role": role,
                "label": label,
                "subject_field": form[mail_helpers.subject_settings_key(role)],
                "body_field": form[mail_helpers.body_settings_key(role)],
            }
            for role, label in (
                (mail_helpers.PROPOSAL_NEW, _("Request received (confirmation)")),
                (mail_helpers.PROPOSAL_ACCEPTED, _("Request accepted")),
                (mail_helpers.PROPOSAL_REJECTED, _("Request rejected")),
            )
        ]
        context["email_placeholders"] = mail_helpers.PLACEHOLDER_DOCS
        context["locales"] = self.request.event.settings.locales
        return context

    def post(self, request, *args, **kwargs):
        form = self.get_form(data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Email templates have been saved."))
            return redirect("plugins:exhibition:email.templates", **event_kwargs(request.event))
        return self.render_to_response(self.get_context_data(form=form))


class EmailTemplatePreviewView(EventPermissionRequiredMixin, View):
    """Render draft template text with sample placeholder values, per locale."""

    permission = "can_change_event_settings"

    def post(self, request, *args, **kwargs):
        role = request.POST.get("role")
        if role not in mail_helpers.LIFECYCLE_ROLES:
            return JsonResponse({"detail": _("Unknown template.")}, status=400)

        from eventyay.base.i18n import language
        from eventyay.base.templatetags.rich_text import markdown_compile_email

        form = ExhibitionMailTemplatesForm(obj=request.event)
        placeholders = mail_helpers.build_preview_placeholders(request.event)
        event_locales = set(request.event.settings.locales)
        region = request.event.settings.region

        def values_by_locale(field_name):
            widget = form.fields[field_name].widget
            raw = widget.value_from_datadict(request.POST, request.FILES, field_name)
            if not isinstance(raw, (list, tuple)):
                raw = [raw]
            locales = getattr(widget, "locales", None) or [code for code, _name in django_settings.LANGUAGES]
            by_locale = {}
            for index, code in enumerate(locales):
                if code in event_locales and index < len(raw):
                    by_locale[code] = raw[index] or ""
            return by_locale

        bodies = values_by_locale(mail_helpers.body_settings_key(role))

        def render(text):
            try:
                return markdown_compile_email(text.format_map(placeholders))
            except (KeyError, IndexError, ValueError):
                return markdown_compile_email(text)

        previews = {}
        for locale in event_locales:
            with language(locale, region):
                previews[locale] = render(bodies.get(locale, ""))
        return JsonResponse({"previews": previews})

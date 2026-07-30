import os
import secrets
import string

from django.conf import settings
from django.db import models
from django.db.models import Max, Q
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.translation import gettext_lazy as _
from eventyay.base.models import Event, Voucher
from eventyay.common.utils.language import localize_event_text
from i18nfield.fields import I18nCharField, I18nTextField
from i18nfield.strings import LazyI18nString

from .social_links import SOCIAL_LINK_CHOICES, get_social_link_spec


def generate_key():
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


def generate_call_secret():
    return secrets.token_urlsafe(24)


def generate_proposal_code():
    alphabet = string.ascii_uppercase + string.digits
    return get_random_string(length=12, allowed_chars=alphabet)


def generate_booth_id(event=None):
    import random
    import string

    # Generate a random booth_id if none exists
    characters = string.ascii_letters + string.digits
    while True:
        booth_id = "".join(random.choices(characters, k=8))  # 8-character random string
        queryset = ExhibitorInfo.objects.filter(booth_id=booth_id)
        if event is not None:
            queryset = queryset.filter(event=event)
        if not queryset.exists():
            return booth_id


def get_next_sponsor_group_level(event):
    if not event:
        return 1
    return (SponsorGroup.objects.filter(event=event).aggregate(max_level=Max("level")).get("max_level") or 0) + 1


def get_next_exhibitor_position(event):
    if not event:
        return 0
    max_position = (
        ExhibitorInfo.objects.filter(event=event, is_exhibitor=True)
        .aggregate(value=Max("exhibitor_position"))
        .get("value")
    )
    return (max_position if max_position is not None else -1) + 1


def get_next_sponsor_position(event, sponsor_group):
    if not event:
        return 0
    max_position = (
        ExhibitorInfo.objects.filter(event=event, is_sponsor=True, sponsor_group=sponsor_group)
        .aggregate(value=Max("sponsor_position"))
        .get("value")
    )
    return (max_position if max_position is not None else -1) + 1


def exhibitor_logo_path(instance, filename):
    name = instance.name
    if isinstance(name, LazyI18nString):
        event = getattr(instance, "event", None)
        locale = getattr(event, "locale", None) if event is not None else None
        name = name.localize(locale) if locale else str(name)
    return os.path.join("exhibitors", "logos", str(name), filename)


def exhibitor_header_image_path(instance, filename):
    name = instance.name
    if isinstance(name, LazyI18nString):
        event = getattr(instance, "event", None)
        locale = getattr(event, "locale", None) if event is not None else None
        name = name.localize(locale) if locale else str(name)
    return os.path.join("exhibitors", "headers", str(name), filename)


def exhibitor_slides_path(instance, filename):
    name = instance.name
    if isinstance(name, LazyI18nString):
        event = getattr(instance, "event", None)
        locale = getattr(event, "locale", None) if event is not None else None
        name = name.localize(locale) if locale else str(name)
    return os.path.join("exhibitors", "slides", str(name), filename)


def proposal_file_path(instance, filename, file_type):
    code = instance.code or "new"
    return os.path.join("exhibition-proposals", str(code), file_type, filename)


def proposal_logo_path(instance, filename):
    return proposal_file_path(instance, filename, "logos")


def proposal_header_image_path(instance, filename):
    return proposal_file_path(instance, filename, "headers")


def proposal_slides_path(instance, filename):
    return proposal_file_path(instance, filename, "slides")


PROPOSAL_DEFAULT_FIELDS = (
    {
        "key": "name",
        "label": _("Organization Name"),
        "active": True,
        "required": True,
        "active_locked": True,
        "required_locked": True,
    },
    {"key": "description", "label": _("Organization Description"), "active": True},
    {"key": "email", "label": _("Contact email"), "active": False},
    {"key": "url", "label": _("Organization Website"), "active": False},
    {"key": "contact_url", "label": _("Contact Page URL"), "active": False},
    {"key": "video_url", "label": _("Promotional Video URL"), "active": False},
    {"key": "slides", "label": _("Promotional Slides"), "active": False},
    {"key": "logo", "label": _("Logo"), "active": False},
    {
        "key": "header_image",
        "label": _("Header Image"),
        "active": False,
    },
    {"key": "booth_name", "label": _("Preferred booth name"), "active": False},
    {
        "key": "notes",
        "label": _("Message to the organizers"),
        "active": False,
    },
    {
        "key": "social_links",
        "label": _("Social Media"),
        "active": False,
        "supports_required": False,
    },
    {
        "key": "extra_links",
        "label": _("Extra Links"),
        "active": False,
        "supports_required": False,
    },
)


PROPOSAL_DEFAULT_FIELD_KEYS = tuple(field["key"] for field in PROPOSAL_DEFAULT_FIELDS)

PROPOSAL_FORMSET_FIELD_KEYS = ("social_links", "extra_links")


def default_proposal_field_settings():
    return {
        field["key"]: {
            "active": field.get("active", True),
            "required": field.get("required", False),
            "position": index,
        }
        for index, field in enumerate(PROPOSAL_DEFAULT_FIELDS)
    }


def get_default_proposal_field_definition(key):
    return next(field for field in PROPOSAL_DEFAULT_FIELDS if field["key"] == key)


def default_allowed_fields():
    return ["attendee_name", "attendee_email"]


class ExhibitorSettings(models.Model):
    event = models.ForeignKey("base.Event", on_delete=models.CASCADE)
    exhibitors_access_mail_subject = models.CharField(max_length=255)
    exhibitors_access_mail_body = models.TextField()
    allowed_fields = models.JSONField(default=default_allowed_fields)
    call_enabled = models.BooleanField(default=False)
    call_headline = I18nCharField(
        max_length=200,
        blank=True,
        verbose_name=_("Call headline"),
    )
    call_text = I18nTextField(
        blank=True,
        verbose_name=_("Call text"),
    )
    call_deadline = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Submission deadline"),
    )
    call_hide_after_deadline = models.BooleanField(default=False)
    call_private = models.BooleanField(default=False)
    call_secret = models.CharField(max_length=64, default=generate_call_secret)
    proposal_field_settings = models.JSONField(default=default_proposal_field_settings)

    def is_field_allowed(self, identifier):
        return identifier in (self.allowed_fields or [])

    @property
    def call_is_open(self):
        if not self.call_enabled:
            return False
        return not self.call_deadline or self.call_deadline >= timezone.now()

    def regenerate_call_secret(self):
        self.call_secret = generate_call_secret()
        self.save(update_fields=["call_secret"])

    @property
    def normalized_proposal_field_settings(self):
        stored_settings = self.proposal_field_settings or {}
        normalized = default_proposal_field_settings()
        for index, field in enumerate(PROPOSAL_DEFAULT_FIELDS):
            key = field["key"]
            stored_field = stored_settings.get(key, {})
            normalized[key]["active"] = bool(stored_field.get("active", normalized[key]["active"]))
            normalized[key]["required"] = bool(stored_field.get("required", normalized[key]["required"]))
            normalized[key]["position"] = stored_field.get("position", index)
            if field.get("active_locked"):
                normalized[key]["active"] = True
            if field.get("required_locked"):
                normalized[key]["required"] = True
            if field.get("supports_required") is False:
                normalized[key]["required"] = False
            if not normalized[key]["active"]:
                normalized[key]["required"] = False
        return normalized

    @property
    def ordered_proposal_field_keys(self):
        normalized = self.normalized_proposal_field_settings
        default_index = {key: i for i, key in enumerate(PROPOSAL_DEFAULT_FIELD_KEYS)}
        return sorted(
            PROPOSAL_DEFAULT_FIELD_KEYS,
            key=lambda key: (normalized[key]["position"], default_index[key]),
        )

    def proposal_field_is_active(self, key):
        return self.normalized_proposal_field_settings[key]["active"]

    def proposal_field_is_required(self, key):
        return self.normalized_proposal_field_settings[key]["required"]

    class Meta:
        unique_together = ("event",)


class SponsorGroup(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="sponsor_groups")
    name = I18nCharField(max_length=120, verbose_name=_("Group Name"))
    level = models.PositiveIntegerField(default=1, db_index=True, verbose_name=_("Level"))
    show_on_front_page = models.BooleanField(
        default=False,
        verbose_name=_("Show this sponsor group on the front page."),
    )

    class Meta:
        ordering = ("level", "pk")

    @property
    def localized_name(self):
        return localize_event_text(self.name) or ""

    def __str__(self):
        return self.localized_name or str(self.name)


class ExhibitorInfo(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    name = I18nCharField(max_length=190, verbose_name=_("Name"))
    description = I18nTextField(verbose_name=_("Description"), null=True, blank=True)
    url = models.URLField(verbose_name=_("URL"), null=True, blank=True)
    email = models.EmailField(verbose_name=_("Email"), null=True, blank=True)
    contact_url = models.URLField(verbose_name=_("Contact URL"), null=True, blank=True)
    video_url = models.URLField(verbose_name=_("Video URL"), null=True, blank=True)
    slides = models.FileField(
        upload_to=exhibitor_slides_path,
        verbose_name=_("Slides"),
        null=True,
        blank=True,
    )
    slides_url = models.URLField(verbose_name=_("Slides URL"), null=True, blank=True)
    logo = models.ImageField(upload_to=exhibitor_logo_path, null=True, blank=True)
    logo_url = models.URLField(verbose_name=_("Logo URL"), null=True, blank=True)
    header_image = models.ImageField(upload_to=exhibitor_header_image_path, null=True, blank=True)
    header_image_url = models.URLField(verbose_name=_("Header Image URL"), null=True, blank=True)
    key = models.CharField(
        max_length=8,
        default=generate_key,
    )
    is_sponsor = models.BooleanField(default=False)
    sponsor_group = models.ForeignKey(
        SponsorGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="partners",
    )
    is_exhibitor = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    booth_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )
    booth_name = I18nCharField(
        max_length=100,
        verbose_name=_("Booth Name"),
        blank=True,
    )
    lead_scanning_enabled = models.BooleanField(default=False)
    allow_voucher_access = models.BooleanField(default=False)
    allow_lead_access = models.BooleanField(default=False)
    lead_scanning_scope_by_device = models.BooleanField(default=False)
    exhibitor_position = models.IntegerField(default=0)
    sponsor_position = models.IntegerField(default=0)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["event", "booth_id"],
                condition=Q(booth_id__isnull=False),
                name="exhibition_event_booth_id_uniq",
            ),
        ]

    def __str__(self):
        return str(self.name)

    def save(self, *args, **kwargs):
        if self._state.adding:
            if self.is_exhibitor and not self.exhibitor_position:
                self.exhibitor_position = get_next_exhibitor_position(self.event)
            if self.is_sponsor and not self.sponsor_position:
                self.sponsor_position = get_next_sponsor_position(self.event, self.sponsor_group)
        super().save(*args, **kwargs)

    @property
    def localized_booth_name(self):
        booth_name = self.booth_name
        if isinstance(booth_name, LazyI18nString):
            locale = getattr(self.event, "locale", None)
            booth_name = booth_name.localize(locale) if locale else str(booth_name)
        return booth_name or ""

    @property
    def visible_logo_url(self):
        if self.logo_url:
            return self.logo_url
        if self.logo:
            return self.logo.url
        return ""

    @property
    def visible_header_image_url(self):
        if self.header_image_url:
            return self.header_image_url
        if self.header_image:
            return self.header_image.url
        return ""

    @property
    def visible_slides_url(self):
        if self.slides_url:
            return self.slides_url
        if self.slides:
            return self.slides.url
        return ""


class ExhibitorSocialLink(models.Model):
    exhibitor = models.ForeignKey(ExhibitorInfo, on_delete=models.CASCADE, related_name="social_links")
    network = models.CharField(max_length=32, choices=SOCIAL_LINK_CHOICES)
    url = models.URLField(verbose_name=_("URL"))

    class Meta:
        ordering = ("network", "url")

    @property
    def spec(self):
        return get_social_link_spec(self.network)

    def __str__(self):
        return f"{self.get_network_display()}: {self.url}"


class ExhibitorExtraLink(models.Model):
    exhibitor = models.ForeignKey(ExhibitorInfo, on_delete=models.CASCADE, related_name="extra_links")
    label = models.CharField(max_length=120, verbose_name=_("Label"))
    url = models.URLField(verbose_name=_("URL"))

    class Meta:
        ordering = ("label", "url")

    def __str__(self):
        return f"{self.label}: {self.url}"


class ExhibitionProposalState(models.TextChoices):
    DRAFT = "draft", _("draft")
    SUBMITTED = "submitted", _("submitted")
    ACCEPTED = "accepted", _("accepted")
    REJECTED = "rejected", _("rejected")
    WITHDRAWN = "withdrawn", _("withdrawn")


class ExhibitionProposal(models.Model):
    code = models.CharField(
        max_length=12,
        unique=True,
        default=generate_proposal_code,
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="exhibition_proposals",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="exhibition_proposals",
    )
    approved_exhibitor = models.ForeignKey(
        ExhibitorInfo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_proposals",
    )
    state = models.CharField(
        max_length=16,
        choices=ExhibitionProposalState.choices,
        default=ExhibitionProposalState.SUBMITTED,
        db_index=True,
    )
    name = I18nCharField(max_length=190, verbose_name=_("Name"))
    description = I18nTextField(verbose_name=_("Description"), null=True, blank=True)
    url = models.URLField(verbose_name=_("URL"), null=True, blank=True)
    email = models.EmailField(verbose_name=_("Email"), null=True, blank=True)
    contact_url = models.URLField(verbose_name=_("Contact URL"), null=True, blank=True)
    video_url = models.URLField(verbose_name=_("Video URL"), null=True, blank=True)
    slides = models.FileField(
        upload_to=proposal_slides_path,
        verbose_name=_("Slides"),
        null=True,
        blank=True,
    )
    slides_url = models.URLField(verbose_name=_("Slides URL"), null=True, blank=True)
    logo = models.ImageField(upload_to=proposal_logo_path, null=True, blank=True)
    logo_url = models.URLField(verbose_name=_("Logo URL"), null=True, blank=True)
    header_image = models.ImageField(upload_to=proposal_header_image_path, null=True, blank=True)
    header_image_url = models.URLField(verbose_name=_("Header Image URL"), null=True, blank=True)
    is_sponsor = models.BooleanField(default=False)
    sponsor_group = models.ForeignKey(
        SponsorGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposals",
    )
    is_exhibitor = models.BooleanField(default=True)
    booth_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )
    booth_name = I18nCharField(
        max_length=100,
        verbose_name=_("Booth Name"),
        blank=True,
    )
    notes = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Message to the organizers"),
    )
    review_notes = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Internal review notes"),
    )
    submitted = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated", "-created")

    def __str__(self):
        return str(self.name)

    @property
    def editable(self):
        return self.state in {
            ExhibitionProposalState.DRAFT,
            ExhibitionProposalState.SUBMITTED,
        }

    def approve(self, requestor=None):
        """Accept the request, create its partner profile and queue the acceptance email."""
        from .mail import PROPOSAL_ACCEPTED, queue_proposal_email
        from .utils import create_exhibitor_from_proposal

        exhibitor = create_exhibitor_from_proposal(self)
        queue_proposal_email(self.event, self, PROPOSAL_ACCEPTED, requestor=requestor)
        return exhibitor

    def reject(self, requestor=None):
        """Reject the request and queue the rejection email."""
        from .mail import PROPOSAL_REJECTED, queue_proposal_email

        self.state = ExhibitionProposalState.REJECTED
        self.save(update_fields=["state", "updated"])
        queue_proposal_email(self.event, self, PROPOSAL_REJECTED, requestor=requestor)

    @property
    def can_be_withdrawn(self):
        return self.state in {
            ExhibitionProposalState.SUBMITTED,
            ExhibitionProposalState.ACCEPTED,
        }

    def withdraw(self):
        self.state = ExhibitionProposalState.WITHDRAWN
        self.save(update_fields=["state", "updated"])
        if self.approved_exhibitor_id and self.approved_exhibitor.active:
            self.approved_exhibitor.active = False
            self.approved_exhibitor.save(update_fields=["active"])

    @property
    def localized_booth_name(self):
        booth_name = self.booth_name
        if isinstance(booth_name, LazyI18nString):
            locale = getattr(self.event, "locale", None)
            booth_name = booth_name.localize(locale) if locale else str(booth_name)
        return booth_name or ""

    @property
    def visible_logo_url(self):
        if self.logo_url:
            return self.logo_url
        if self.logo:
            return self.logo.url
        return ""

    @property
    def visible_header_image_url(self):
        if self.header_image_url:
            return self.header_image_url
        if self.header_image:
            return self.header_image.url
        return ""

    @property
    def visible_slides_url(self):
        if self.slides_url:
            return self.slides_url
        if self.slides:
            return self.slides.url
        return ""


class ExhibitionProposalSocialLink(models.Model):
    proposal = models.ForeignKey(ExhibitionProposal, on_delete=models.CASCADE, related_name="social_links")
    network = models.CharField(max_length=32, choices=SOCIAL_LINK_CHOICES)
    url = models.URLField(verbose_name=_("URL"))

    class Meta:
        ordering = ("network", "url")

    @property
    def spec(self):
        return get_social_link_spec(self.network)

    def __str__(self):
        return f"{self.get_network_display()}: {self.url}"


class ExhibitionProposalExtraLink(models.Model):
    proposal = models.ForeignKey(ExhibitionProposal, on_delete=models.CASCADE, related_name="extra_links")
    label = models.CharField(max_length=120, verbose_name=_("Label"))
    url = models.URLField(verbose_name=_("URL"))

    class Meta:
        ordering = ("label", "url")

    def __str__(self):
        return f"{self.label}: {self.url}"


class ExhibitionQuestionVariant(models.TextChoices):
    STRING = "string", _("Text (one-line)")
    TEXT = "text", _("Multi-line text")
    URL = "url", _("URL")
    BOOLEAN = "boolean", _("Confirmation")
    CHOICES = "choices", _("Radio button (Choose one option)")
    MULTIPLE = "multiple_choice", _("Checkbox (Choose one or several options)")
    SELECT = "select", _("Select (one option)")


class ExhibitionQuestion(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="exhibition_questions",
    )
    variant = models.CharField(
        max_length=32,
        choices=ExhibitionQuestionVariant.choices,
        default=ExhibitionQuestionVariant.STRING,
    )
    question = I18nCharField(max_length=800, verbose_name=_("Custom question"))
    help_text = I18nCharField(
        null=True,
        blank=True,
        max_length=800,
        verbose_name=_("help text"),
    )
    required = models.BooleanField(default=False, verbose_name=_("required"))
    active = models.BooleanField(default=True, verbose_name=_("active"))
    position = models.IntegerField(default=0)

    class Meta:
        ordering = ("position", "id")

    @property
    def localized_question(self):
        return localize_event_text(self.question) or ""

    def __str__(self):
        return self.localized_question or str(self.question)


class ExhibitionQuestionOption(models.Model):
    question = models.ForeignKey(
        ExhibitionQuestion,
        on_delete=models.CASCADE,
        related_name="options",
    )
    answer = I18nCharField(verbose_name=_("Response"))
    position = models.IntegerField(default=0)

    class Meta:
        ordering = ("position", "id")

    def __str__(self):
        return localize_event_text(self.answer) or str(self.answer)


class ExhibitionAnswer(models.Model):
    question = models.ForeignKey(
        ExhibitionQuestion,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    proposal = models.ForeignKey(
        ExhibitionProposal,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    answer = models.TextField(blank=True)
    options = models.ManyToManyField(ExhibitionQuestionOption, related_name="answers")

    class Meta:
        unique_together = ("question", "proposal")

    @property
    def answer_string(self):
        if self.question.variant == ExhibitionQuestionVariant.BOOLEAN:
            if self.answer == "True":
                return _("Yes")
            if self.answer == "False":
                return _("No")
            return ""
        if self.question.variant in {
            ExhibitionQuestionVariant.CHOICES,
            ExhibitionQuestionVariant.MULTIPLE,
            ExhibitionQuestionVariant.SELECT,
        }:
            return ", ".join(str(option) for option in self.options.all())
        return self.answer or ""


class Lead(models.Model):
    exhibitor = models.ForeignKey(ExhibitorInfo, on_delete=models.CASCADE)
    exhibitor_name = models.CharField(max_length=190)
    pseudonymization_id = models.CharField(max_length=190)
    scanned = models.DateTimeField()
    scan_type = models.CharField(max_length=50)
    device_name = models.CharField(max_length=50)
    attendee = models.JSONField(null=True, blank=True)
    booth_id = models.CharField(max_length=100, editable=True)
    booth_name = models.CharField(
        max_length=100,
        verbose_name=_("Booth Name"),
    )

    def __str__(self):
        return f"Lead scanned by {self.exhibitor.name}"


class ExhibitorTag(models.Model):
    exhibitor = models.ForeignKey(ExhibitorInfo, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=50)
    use_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("exhibitor", "name")
        ordering = ["-use_count", "name"]

    def __str__(self):
        return f"{self.name} ({self.exhibitor.name})"


class ExhibitorVoucher(models.Model):
    exhibitor = models.ForeignKey(ExhibitorInfo, on_delete=models.CASCADE, related_name="vouchers")
    voucher = models.OneToOneField(Voucher, on_delete=models.CASCADE, related_name="exhibitor_link")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created",)

    def __str__(self):
        return f"{self.voucher.code} ({self.exhibitor.name})"


class ExhibitionEmailQueue(models.Model):
    """A single email queued for one recipient, with placeholders already rendered."""

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="exhibition_email_queue",
    )
    proposal = models.ForeignKey(
        ExhibitionProposal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="emails",
    )
    exhibitor = models.ForeignKey(
        ExhibitorInfo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="emails",
    )
    batch = models.UUIDField(null=True, blank=True, db_index=True)
    to_email = models.EmailField(verbose_name=_("Recipient"))
    subject = models.CharField(max_length=255, verbose_name=_("Subject"))
    body = models.TextField(verbose_name=_("Body"))
    reply_to = models.CharField(max_length=255, blank=True, default="")
    locale = models.CharField(max_length=32, blank=True, default="")
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Queued email")
        verbose_name_plural = _("Queued emails")
        ordering = ("-created",)

    def __str__(self):
        state = "sent" if self.sent_at else "pending"
        return f"{self.to_email} · {state} · {self.subject}"

    def send(self, requestor=None):
        """Deliver the email via the core mail() service and mark it sent."""
        from eventyay.base.services.mail import mail

        if self.sent_at:
            return

        mail(
            email=self.to_email,
            subject=self.subject,
            template=LazyI18nString(self.body),
            context={},
            event=self.event,
            locale=self.locale or None,
            auto_email=False,
            event_reply_to=self.reply_to or None,
        )
        self.sent_at = timezone.now()
        self.scheduled_at = None
        self.save(update_fields=["sent_at", "scheduled_at", "updated"])
        self.event.log_action(
            "eventyay.plugins.exhibition.email.sent",
            user=requestor,
            data={"queue_id": self.pk, "to": self.to_email, "subject": self.subject},
        )

    send.alters_data = True

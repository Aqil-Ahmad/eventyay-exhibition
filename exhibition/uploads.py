from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile, UploadedFile
from django.urls import reverse
from django.utils.timezone import now
from eventyay.base.models import CachedFile

RETAINED_UPLOAD_SUFFIX = "-retained"
RETAINED_UPLOAD_DAYS = 1


def retained_upload_url(cached_file):
    return reverse("cachedfile.download", kwargs={"id": cached_file.id})


class RetainedFileInput(forms.ClearableFileInput):
    """A file input that also carries a file kept from a failed submit, so it is not lost."""

    template_name = "exhibitors/widgets/retained_file_input.html"

    def __init__(self, attrs=None, retained=None):
        super().__init__(attrs)
        self.retained = retained

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["retained"] = self.retained
        context["widget"]["retained_name"] = name + RETAINED_UPLOAD_SUFFIX
        context["widget"]["retained_url"] = retained_upload_url(self.retained)
        return context


class RetainedUploadsMixin:
    """Keep the files of a failed submit and put them back on the next one, as browsers cannot refill file inputs."""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if "files" in kwargs:
            kwargs["files"] = self.restore_retained_uploads(kwargs["data"], kwargs["files"])
        return kwargs

    def form_invalid(self, form):
        self.retain_uploads(form)
        return super().form_invalid(form)

    def retained_upload_session_key(self):
        session = self.request.session
        if not getattr(session, "session_key", None) and hasattr(session, "save"):
            session.save()
        return getattr(session, "session_key", None)

    def find_retained_upload(self, cached_file_id):
        session_key = self.retained_upload_session_key()
        if not session_key:
            return None
        try:
            return CachedFile.objects.filter(id=cached_file_id, session_key=session_key, expires__gt=now()).first()
        except (ValueError, ValidationError):
            return None

    def restore_retained_uploads(self, data, files):
        files = files.copy()
        for key in data:
            if not key.endswith(RETAINED_UPLOAD_SUFFIX):
                continue
            name = key[: -len(RETAINED_UPLOAD_SUFFIX)]
            if files.get(name) or data.get(f"{name}-clear"):
                continue
            cached_file = self.find_retained_upload(data.get(key))
            if cached_file is None or not cached_file.file:
                continue
            with cached_file.file.open("rb") as stored:
                upload = SimpleUploadedFile(cached_file.filename, stored.read(), content_type=cached_file.type)
            upload.retained_from = cached_file
            files[name] = upload
        return files

    def cache_upload(self, upload):
        session_key = self.retained_upload_session_key()
        if not session_key:
            return None
        cached_file = CachedFile.objects.create(
            expires=now() + timedelta(days=RETAINED_UPLOAD_DAYS),
            date=now(),
            web_download=True,
            filename=upload.name,
            type=upload.content_type or "application/octet-stream",
            session_key=session_key,
        )
        upload.seek(0)
        cached_file.file.save(upload.name, upload, save=True)
        return cached_file

    def retain_uploads(self, form):
        form.retained_upload_urls = {}
        for name, field in form.fields.items():
            if not isinstance(field, forms.FileField) or name in form.errors:
                continue
            upload = form.files.get(form.add_prefix(name))
            if not isinstance(upload, UploadedFile):
                continue
            cached_file = getattr(upload, "retained_from", None) or self.cache_upload(upload)
            if cached_file is None:
                continue
            widget = RetainedFileInput(attrs=field.widget.attrs, retained=cached_file)
            widget.is_required = field.widget.is_required
            field.widget = widget
            form.retained_upload_urls[name] = retained_upload_url(cached_file)

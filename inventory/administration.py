from django import forms
from django.contrib import messages
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.forms import SetPasswordForm, UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, FormView, ListView, UpdateView

User = get_user_model()


class SuperuserRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_active and self.request.user.is_staff and self.request.user.is_superuser


def record_admin_action(request, obj, action, message):
    LogEntry.objects.log_action(
        user_id=request.user.pk,
        content_type_id=ContentType.objects.get_for_model(obj).pk,
        object_id=obj.pk,
        object_repr=str(obj),
        action_flag=action,
        change_message=message,
    )


class PermissionChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, permission):
        return f"{permission.content_type.app_label} | {permission.content_type.model} | {permission.name}"


def permission_field():
    return PermissionChoiceField(
        queryset=Permission.objects.select_related("content_type").order_by(
            "content_type__app_label", "content_type__model", "codename",
        ),
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 12}),
        help_text="Hold Ctrl (or Command on macOS) to select multiple permissions.",
    )


class UserFieldsMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["groups"] = forms.ModelMultipleChoiceField(
            queryset=Group.objects.order_by("name"), required=False,
            widget=forms.SelectMultiple(attrs={"size": 6}),
            help_text="Hold Ctrl (or Command on macOS) to select multiple groups.",
        )
        self.fields["user_permissions"] = permission_field()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("is_superuser") and not cleaned.get("is_staff"):
            self.add_error("is_staff", "A superuser must have staff access to use administration.")
        return cleaned


USER_FIELDS = [
    "username", "first_name", "last_name", "email", "is_active", "is_staff",
    "is_superuser", "groups", "user_permissions",
]


class ManagedUserCreationForm(UserFieldsMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = USER_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["is_staff"].initial = True


class ManagedUserChangeForm(UserFieldsMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = USER_FIELDS


class ManagedGroupForm(forms.ModelForm):
    permissions = permission_field()

    class Meta:
        model = Group
        fields = ["name", "permissions"]


class UserListView(SuperuserRequiredMixin, ListView):
    model = User
    template_name = "inventory/administration/users.html"
    context_object_name = "accounts"
    paginate_by = 20

    def get_queryset(self):
        queryset = User.objects.order_by("username", "pk").prefetch_related("groups")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(username__icontains=query) | Q(first_name__icontains=query) |
                Q(last_name__icontains=query) | Q(email__icontains=query)
            )
        return queryset


class GroupListView(SuperuserRequiredMixin, ListView):
    model = Group
    template_name = "inventory/administration/groups.html"
    context_object_name = "groups"
    paginate_by = 20

    def get_queryset(self):
        queryset = Group.objects.order_by("name", "pk").prefetch_related("permissions")
        query = self.request.GET.get("q", "").strip()
        return queryset.filter(name__icontains=query) if query else queryset


class ManagedFormMixin:
    template_name = "inventory/administration/form.html"
    success_url = reverse_lazy("administration_users")

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            record_admin_action(
                self.request, self.object,
                ADDITION if self.is_creation else CHANGE,
                "Created in PIMS administration." if self.is_creation else "Updated in PIMS administration.",
            )
        messages.success(self.request, "Changes saved.")
        return response


class UserCreateView(SuperuserRequiredMixin, ManagedFormMixin, CreateView):
    model = User
    form_class = ManagedUserCreationForm
    is_creation = True
    extra_context = {"title": "Create user", "cancel_url": "administration_users"}


class UserUpdateView(SuperuserRequiredMixin, ManagedFormMixin, UpdateView):
    model = User
    form_class = ManagedUserChangeForm
    is_creation = False
    extra_context = {"title": "Edit user", "cancel_url": "administration_users"}

    def form_valid(self, form):
        with transaction.atomic():
            # Lock accounts in a consistent order when checking administrator availability.
            locked = list(User.objects.select_for_update().order_by("pk"))
            current = next((user for user in locked if user.pk == self.object.pk), None)
            if current is None:
                form.add_error(None, "This account no longer exists.")
                return self.form_invalid(form)
            loses_admin = not (
                form.cleaned_data["is_active"] and form.cleaned_data["is_staff"]
                and form.cleaned_data["is_superuser"]
            )
            if self.object.pk == self.request.user.pk and loses_admin:
                form.add_error(None, "You cannot deactivate or remove your own administrator access.")
                return self.form_invalid(form)
            if current.is_active and current.is_staff and current.is_superuser and loses_admin:
                if not any(
                    user.pk != current.pk and user.is_active and user.is_staff and user.is_superuser
                    for user in locked
                ):
                    form.add_error(None, "At least one active staff superuser must remain.")
                    return self.form_invalid(form)
            return super().form_valid(form)


class UserPasswordView(SuperuserRequiredMixin, FormView):
    template_name = "inventory/administration/form.html"
    form_class = SetPasswordForm
    success_url = reverse_lazy("administration_users")
    extra_context = {"title": "Reset user password", "cancel_url": "administration_users"}

    def get_user(self):
        return get_object_or_404(User, pk=self.kwargs["pk"])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.get_user()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["note"] = f"Set a new password for {self.get_user().get_username()}. Share it securely."
        return context

    def form_valid(self, form):
        with transaction.atomic():
            user = form.save()
            record_admin_action(self.request, user, CHANGE, "Password reset in PIMS administration.")
        if user.pk == self.request.user.pk:
            update_session_auth_hash(self.request, user)
        messages.success(self.request, "Password updated. Other sessions for this account are invalidated.")
        return super().form_valid(form)


class UserDeleteView(SuperuserRequiredMixin, DeleteView):
    model = User
    template_name = "inventory/administration/confirm_delete.html"
    success_url = reverse_lazy("administration_users")
    extra_context = {"kind": "user", "cancel_url": "administration_users"}

    def form_valid(self, form):
        with transaction.atomic():
            locked = list(User.objects.select_for_update().order_by("pk"))
            current = next((user for user in locked if user.pk == self.object.pk), None)
            if current is None:
                messages.error(self.request, "This account no longer exists.")
                return redirect(self.success_url)
            if current.pk == self.request.user.pk:
                messages.error(self.request, "You cannot delete your own account.")
                return redirect(self.success_url)
            if current.is_active and current.is_staff and current.is_superuser and not any(
                user.pk != current.pk and user.is_active and user.is_staff and user.is_superuser
                for user in locked
            ):
                messages.error(self.request, "At least one active staff superuser must remain.")
                return redirect(self.success_url)
            try:
                with transaction.atomic():
                    record_admin_action(self.request, current, DELETION, "Deleted in PIMS administration.")
                    response = super().form_valid(form)
            except ProtectedError:
                messages.error(self.request, "This account has stock history and cannot be deleted. Deactivate it instead.")
                return redirect(self.success_url)
        messages.success(self.request, "User deleted.")
        return response


class GroupCreateView(SuperuserRequiredMixin, ManagedFormMixin, CreateView):
    model = Group
    form_class = ManagedGroupForm
    success_url = reverse_lazy("administration_groups")
    is_creation = True
    extra_context = {"title": "Create group", "cancel_url": "administration_groups"}


class GroupUpdateView(SuperuserRequiredMixin, ManagedFormMixin, UpdateView):
    model = Group
    form_class = ManagedGroupForm
    success_url = reverse_lazy("administration_groups")
    is_creation = False
    extra_context = {"title": "Edit group", "cancel_url": "administration_groups"}


class GroupDeleteView(SuperuserRequiredMixin, DeleteView):
    model = Group
    template_name = "inventory/administration/confirm_delete.html"
    success_url = reverse_lazy("administration_groups")
    extra_context = {"kind": "group", "cancel_url": "administration_groups"}

    def form_valid(self, form):
        with transaction.atomic():
            record_admin_action(self.request, self.object, DELETION, "Deleted in PIMS administration.")
            response = super().form_valid(form)
        messages.success(self.request, "Group deleted. Its members were not deleted.")
        return response

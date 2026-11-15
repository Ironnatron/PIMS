from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import F, Q, Sum
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView

from .forms import AdjustmentForm, BatchForm, ProductForm, SupplierForm
from .models import Batch, Product, StockAdjustment, Supplier
from .services import adjust_stock


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


def products_with_stock():
    return Product.objects.annotate(stock=Coalesce(Sum(
        "batches__quantity",
        filter=Q(batches__expiry_date__gte=timezone.localdate(), batches__supplier__is_active=True),
    ), 0)).order_by("name", "pk")


class DashboardView(StaffRequiredMixin, TemplateView):
    template_name = "inventory/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        products = products_with_stock().filter(is_active=True)
        stocked = Batch.objects.filter(quantity__gt=0)
        low = products.filter(stock__lte=F("reorder_level"))
        expiring = stocked.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=90))
        expired = stocked.filter(expiry_date__lt=today)
        context.update(
            product_count=products.count(),
            supplier_count=Supplier.objects.filter(is_active=True).count(),
            low_count=low.count(), expiring_count=expiring.count(), expired_count=expired.count(),
            low_products=low[:8],
            expiring_batches=expiring.select_related("product", "supplier")[:8],
            adjustments=StockAdjustment.objects.select_related("batch__product", "user")[:8],
        )
        return context


class ProductListView(StaffRequiredMixin, ListView):
    template_name = "inventory/product_list.html"
    context_object_name = "products"
    paginate_by = 20

    def get_queryset(self):
        queryset = products_with_stock()
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) | Q(sku__icontains=query) |
                Q(generic_name__icontains=query) | Q(manufacturer__icontains=query)
            )
        kind = self.request.GET.get("kind")
        if kind in Product.Kind.values:
            queryset = queryset.filter(kind=kind)
        status = self.request.GET.get("status")
        if status in ("active", "inactive"):
            queryset = queryset.filter(is_active=status == "active")
        if self.request.GET.get("stock") == "low":
            queryset = queryset.filter(is_active=True, stock__lte=F("reorder_level"))
        return queryset


class ProductDetailView(StaffRequiredMixin, DetailView):
    model = Product
    template_name = "inventory/product_detail.html"

    def get_queryset(self):
        return products_with_stock()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["batches"] = self.object.batches.select_related("supplier")
        context["today"] = timezone.localdate()
        return context


class SavedMessageMixin:
    template_name = "inventory/form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Record saved.")
        return response


class ProductCreateView(StaffRequiredMixin, SavedMessageMixin, CreateView):
    model = Product
    form_class = ProductForm
    extra_context = {"title": "Add medicine / product"}

    def get_success_url(self):
        return reverse_lazy("product_detail", kwargs={"pk": self.object.pk})


class ProductUpdateView(StaffRequiredMixin, SavedMessageMixin, UpdateView):
    model = Product
    form_class = ProductForm
    extra_context = {"title": "Edit medicine / product"}

    def get_success_url(self):
        return reverse_lazy("product_detail", kwargs={"pk": self.object.pk})


class SupplierListView(StaffRequiredMixin, ListView):
    model = Supplier
    template_name = "inventory/supplier_list.html"
    context_object_name = "suppliers"
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) | Q(contact_person__icontains=query) |
                Q(phone__icontains=query) | Q(email__icontains=query)
            )
        return queryset


class SupplierDetailView(StaffRequiredMixin, DetailView):
    model = Supplier
    template_name = "inventory/supplier_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["batches"] = self.object.batches.select_related("product")
        return context


class SupplierCreateView(StaffRequiredMixin, SavedMessageMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    extra_context = {"title": "Add supplier"}

    def get_success_url(self):
        return reverse_lazy("supplier_detail", kwargs={"pk": self.object.pk})


class SupplierUpdateView(StaffRequiredMixin, SavedMessageMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    extra_context = {"title": "Edit supplier"}

    def get_success_url(self):
        return reverse_lazy("supplier_detail", kwargs={"pk": self.object.pk})


class ProtectedDeleteView(StaffRequiredMixin, DeleteView):
    template_name = "inventory/confirm_delete.html"

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, "This record has batch history and cannot be deleted. Mark it inactive instead.")
            return redirect(self.success_url)
        messages.success(self.request, "Record deleted.")
        return response


class ProductDeleteView(ProtectedDeleteView):
    model = Product
    success_url = reverse_lazy("product_list")


class SupplierDeleteView(ProtectedDeleteView):
    model = Supplier
    success_url = reverse_lazy("supplier_list")


class BatchListView(StaffRequiredMixin, ListView):
    model = Batch
    template_name = "inventory/batch_list.html"
    context_object_name = "batches"
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset().select_related("product", "supplier")
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(batch_number__icontains=query) | Q(product__name__icontains=query) |
                Q(product__sku__icontains=query) | Q(supplier__name__icontains=query)
            )
        today = timezone.localdate()
        status = self.request.GET.get("status")
        if status == "expired":
            queryset = queryset.filter(expiry_date__lt=today, quantity__gt=0)
        elif status == "expiring":
            queryset = queryset.filter(
                expiry_date__gte=today, expiry_date__lte=today + timedelta(days=90), quantity__gt=0,
            )
        elif status == "usable":
            queryset = queryset.filter(
                expiry_date__gte=today, quantity__gt=0, product__is_active=True, supplier__is_active=True,
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["today"] = timezone.localdate()
        return context


class BatchCreateView(StaffRequiredMixin, SavedMessageMixin, CreateView):
    model = Batch
    form_class = BatchForm
    extra_context = {
        "title": "Add batch",
        "note": "New batches start at zero stock. Receive stock using Adjust stock after saving.",
    }

    def get_initial(self):
        initial = super().get_initial()
        initial["product"] = self.request.GET.get("product")
        return initial

    def get_success_url(self):
        return reverse_lazy("batch_adjust", kwargs={"pk": self.object.pk})


class BatchUpdateView(StaffRequiredMixin, SavedMessageMixin, UpdateView):
    model = Batch
    form_class = BatchForm
    extra_context = {
        "title": "Edit batch",
        "note": "Batch identity is fixed to preserve stock history. Quantity changes require an adjustment.",
    }

    def get_success_url(self):
        return reverse_lazy("batch_list")


class BatchAdjustmentView(StaffRequiredMixin, FormView):
    form_class = AdjustmentForm
    template_name = "inventory/adjustment.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        batch = get_object_or_404(Batch.objects.select_related("product", "supplier"), pk=self.kwargs["pk"])
        context["batch"] = batch
        context["adjustments"] = batch.adjustments.select_related("user")[:50]
        return context

    def form_valid(self, form):
        get_object_or_404(Batch, pk=self.kwargs["pk"])
        try:
            adjust_stock(
                batch_id=self.kwargs["pk"], user=self.request.user,
                change=form.cleaned_data["change"], reason=form.cleaned_data["reason"],
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, "Stock adjusted and recorded in history.")
        return redirect("batch_adjust", pk=self.kwargs["pk"])


def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})

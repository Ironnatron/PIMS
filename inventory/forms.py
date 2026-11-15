from django import forms
from django.utils import timezone

from .models import Batch, Product, Supplier


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "sku", "name", "kind", "generic_name", "manufacturer", "strength",
            "dosage_form", "unit", "requires_prescription", "reorder_level",
            "description", "is_active",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def clean_sku(self):
        sku = self.cleaned_data["sku"].strip().upper()
        if Product.objects.filter(sku__iexact=sku).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A product with this SKU already exists.")
        return sku


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            "name", "contact_person", "email", "phone", "address", "tax_id",
            "license_number", "is_active",
        ]
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}


class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = [
            "product", "supplier", "batch_number", "received_date", "manufacture_date",
            "expiry_date", "purchase_price", "selling_price",
        ]
        widgets = {
            field: forms.DateInput(attrs={"type": "date"})
            for field in ["received_date", "manufacture_date", "expiry_date"]
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Keep the stock ledger associated with its original product and supplier.
            self.fields["product"].disabled = True
            self.fields["supplier"].disabled = True
            self.fields["batch_number"].disabled = True
        else:
            self.fields["product"].queryset = Product.objects.filter(is_active=True)
            self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True)
            self.fields["received_date"].initial = timezone.localdate

    def clean_received_date(self):
        value = self.cleaned_data["received_date"]
        if value > timezone.localdate():
            raise forms.ValidationError("Receipt date cannot be in the future.")
        return value


class AdjustmentForm(forms.Form):
    change = forms.IntegerField(
        min_value=-2147483647, max_value=2147483647,
        help_text="Positive to receive stock, negative to remove stock. Count in the product's stock unit.",
    )
    reason = forms.CharField(max_length=240, widget=forms.Textarea(attrs={"rows": 3}))

    def clean_change(self):
        value = self.cleaned_data["change"]
        if value == 0:
            raise forms.ValidationError("Stock change cannot be zero.")
        return value

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Supplier(models.Model):
    name = models.CharField(max_length=160)
    contact_person = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    tax_id = models.CharField("Tax / GST ID", max_length=40, blank=True)
    license_number = models.CharField("Drug license number", max_length=80, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "pk"]

    def __str__(self):
        return self.name


class Product(models.Model):
    class Kind(models.TextChoices):
        MEDICINE = "medicine", "Medicine"
        OTHER = "other", "Other product"

    sku = models.CharField("SKU", max_length=50, unique=True)
    name = models.CharField(max_length=180)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.MEDICINE)
    generic_name = models.CharField(max_length=180, blank=True)
    manufacturer = models.CharField(max_length=160, blank=True)
    strength = models.CharField(max_length=80, blank=True)
    dosage_form = models.CharField(max_length=80, blank=True)
    unit = models.CharField(max_length=50, default="pack", help_text="Stock counting unit, e.g. box, strip or bottle.")
    requires_prescription = models.BooleanField(default=False)
    reorder_level = models.PositiveIntegerField(default=10)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "pk"]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    def clean(self):
        super().clean()
        if self.pk and self.batches.exists():
            original_unit = type(self).objects.values_list("unit", flat=True).get(pk=self.pk)
            if self.unit != original_unit:
                raise ValidationError({"unit": "The stock unit cannot change after batches exist. Create a new SKU instead."})
        if self.kind == self.Kind.OTHER and self.requires_prescription:
            raise ValidationError({"requires_prescription": "Only medicines can require a prescription."})


class Batch(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="batches")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="batches")
    batch_number = models.CharField(max_length=80)
    received_date = models.DateField()
    manufacture_date = models.DateField(blank=True, null=True)
    expiry_date = models.DateField(help_text="The batch is usable through this date.")
    quantity = models.PositiveIntegerField(default=0, editable=False)
    purchase_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))],
    )
    selling_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["expiry_date", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["product", "batch_number"], name="unique_product_batch"),
            models.CheckConstraint(condition=Q(quantity__gte=0), name="nonnegative_batch_quantity"),
            models.CheckConstraint(condition=Q(purchase_price__gte=0), name="nonnegative_purchase_price"),
            models.CheckConstraint(condition=Q(selling_price__gte=0), name="nonnegative_selling_price"),
            models.CheckConstraint(
                condition=Q(expiry_date__gte=models.F("received_date")), name="expiry_after_receipt",
            ),
            models.CheckConstraint(
                condition=Q(manufacture_date__isnull=True) | Q(manufacture_date__lte=models.F("received_date")),
                name="manufacture_before_receipt",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.batch_number}"

    def clean(self):
        super().clean()
        if self.expiry_date and self.received_date and self.expiry_date < self.received_date:
            raise ValidationError({"expiry_date": "Expiry cannot be before receipt."})
        if self.manufacture_date and self.received_date and self.manufacture_date > self.received_date:
            raise ValidationError({"manufacture_date": "Manufacture cannot be after receipt."})


class StockAdjustment(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="adjustments")
    change = models.IntegerField()
    resulting_quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=240)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(condition=~Q(change=0), name="nonzero_stock_adjustment"),
        ]

    def __str__(self):
        return f"{self.batch} ({self.change:+d})"

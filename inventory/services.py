from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Batch, StockAdjustment


@transaction.atomic
def adjust_stock(*, batch_id, change, reason, user):
    if not isinstance(change, int) or isinstance(change, bool) or change == 0:
        raise ValidationError("Enter a nonzero whole-number stock change.")
    reason = reason.strip()
    if not reason or len(reason) > 240:
        raise ValidationError("A reason of 1 to 240 characters is required.")
    batch = Batch.objects.select_for_update().select_related("product", "supplier").get(pk=batch_id)
    if change > 0:
        if not batch.product.is_active or not batch.supplier.is_active:
            raise ValidationError("Reactivate the product and supplier before receiving stock.")
        if batch.expiry_date < timezone.localdate():
            raise ValidationError("Cannot receive stock into an expired batch.")
    quantity = batch.quantity + change
    if quantity < 0:
        raise ValidationError("Stock cannot go below zero.")
    if quantity > 2147483647:
        raise ValidationError("Stock exceeds the supported quantity limit.")
    batch.quantity = quantity
    batch.save(update_fields=["quantity"])
    return StockAdjustment.objects.create(
        batch=batch, change=change, resulting_quantity=quantity, reason=reason, user=user,
    )

from django.contrib import admin

from .models import Batch, Product, StockAdjustment, Supplier


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "kind", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("sku", "name", "generic_name")
    readonly_fields = ("created_at",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_person", "phone", "is_active")
    search_fields = ("name", "email", "phone")
    readonly_fields = ("created_at",)


class ReadOnlyInventoryAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Batch)
class BatchAdmin(ReadOnlyInventoryAdmin):
    list_display = ("product", "batch_number", "supplier", "quantity", "expiry_date")
    search_fields = ("product__name", "batch_number")


@admin.register(StockAdjustment)
class AdjustmentAdmin(ReadOnlyInventoryAdmin):
    list_display = ("batch", "change", "resulting_quantity", "reason", "user", "created_at")
    search_fields = ("batch__batch_number", "reason")

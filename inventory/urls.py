from django.urls import path

from . import administration, views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("administration/", administration.UserListView.as_view(), name="administration_users"),
    path("administration/users/add/", administration.UserCreateView.as_view(), name="administration_user_add"),
    path("administration/users/<int:pk>/edit/", administration.UserUpdateView.as_view(), name="administration_user_edit"),
    path("administration/users/<int:pk>/password/", administration.UserPasswordView.as_view(), name="administration_user_password"),
    path("administration/users/<int:pk>/delete/", administration.UserDeleteView.as_view(), name="administration_user_delete"),
    path("administration/groups/", administration.GroupListView.as_view(), name="administration_groups"),
    path("administration/groups/add/", administration.GroupCreateView.as_view(), name="administration_group_add"),
    path("administration/groups/<int:pk>/edit/", administration.GroupUpdateView.as_view(), name="administration_group_edit"),
    path("administration/groups/<int:pk>/delete/", administration.GroupDeleteView.as_view(), name="administration_group_delete"),
    path("products/", views.ProductListView.as_view(), name="product_list"),
    path("products/add/", views.ProductCreateView.as_view(), name="product_add"),
    path("products/<int:pk>/", views.ProductDetailView.as_view(), name="product_detail"),
    path("products/<int:pk>/edit/", views.ProductUpdateView.as_view(), name="product_edit"),
    path("products/<int:pk>/delete/", views.ProductDeleteView.as_view(), name="product_delete"),
    path("suppliers/", views.SupplierListView.as_view(), name="supplier_list"),
    path("suppliers/add/", views.SupplierCreateView.as_view(), name="supplier_add"),
    path("suppliers/<int:pk>/", views.SupplierDetailView.as_view(), name="supplier_detail"),
    path("suppliers/<int:pk>/edit/", views.SupplierUpdateView.as_view(), name="supplier_edit"),
    path("suppliers/<int:pk>/delete/", views.SupplierDeleteView.as_view(), name="supplier_delete"),
    path("batches/", views.BatchListView.as_view(), name="batch_list"),
    path("batches/add/", views.BatchCreateView.as_view(), name="batch_add"),
    path("batches/<int:pk>/edit/", views.BatchUpdateView.as_view(), name="batch_edit"),
    path("batches/<int:pk>/adjust/", views.BatchAdjustmentView.as_view(), name="batch_adjust"),
]

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("documents", views.DocumentViewSet, basename="document")

doc = "documents/<uuid:document_id>"
urlpatterns = [
    path(f"{doc}/versions/", views.VersionListCreateView.as_view()),
    path(f"{doc}/versions/<uuid:version_id>/download/", views.VersionDownloadView.as_view()),
    path(f"{doc}/versions/<uuid:version_id>/download-link/", views.DownloadLinkView.as_view()),
    path(f"{doc}/versions/<uuid:version_id>/comments/", views.CommentListCreateView.as_view()),
    path(f"{doc}/versions/<uuid:version_id>/review/", views.ReviewView.as_view()),
    path(f"{doc}/access/", views.AccessListCreateView.as_view()),
    path(f"{doc}/access/<str:username>/", views.AccessRevokeView.as_view()),
    path("downloads/<str:token>/", views.SignedDownloadView.as_view()),
    path("", include(router.urls)),
]

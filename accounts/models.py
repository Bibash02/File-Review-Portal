from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.
class User(AbstractUser):
    class Role(models.TextChoices):
        CLIENT = "client", "Client"
        REVIEWER = "reviewer", "Reviewer"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CLIENT)
    
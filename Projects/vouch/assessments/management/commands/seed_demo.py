"""Seed demo users, a Restaurants category with criteria, and a sample assessment."""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from assessments.models import Profile, Category, Criterion, Assessment, Role, Stage


DEMO_USERS = [
    ("admin", "admin123", Role.ADMIN, True),
    ("assessor", "assessor123", Role.ASSESSOR, False),
    ("reviewer", "reviewer123", Role.REVIEWER, False),
    ("business", "business123", Role.BUSINESS, False),
]

RESTAURANT_CRITERIA = [
    ("Food hygiene and kitchen standards", 3, 10),
    ("Ingredient sourcing and transparency", 2, 10),
    ("Staff training and certification", 2, 10),
    ("Customer complaint handling", 1, 10),
    ("Licensing and legal compliance", 3, 10),
    ("Cleanliness of premises", 2, 10),
]


class Command(BaseCommand):
    help = "Create demo data for the VOUCH prototype."

    def handle(self, *args, **options):
        users = {}
        for username, pwd, role, is_super in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"is_staff": is_super, "is_superuser": is_super},
            )
            if created:
                user.set_password(pwd)
                user.save()
            Profile.objects.update_or_create(user=user, defaults={"role": role})
            users[role] = user
        self.stdout.write(self.style.SUCCESS("Users ready."))

        category, _ = Category.objects.get_or_create(
            name="Restaurants",
            defaults={"description": "Trust assessment for restaurants and food service."},
        )
        for order, (name, weight, mx) in enumerate(RESTAURANT_CRITERIA):
            Criterion.objects.get_or_create(
                category=category, name=name,
                defaults={"weight": weight, "max_score": mx, "order": order},
            )
        self.stdout.write(self.style.SUCCESS("Restaurants category + criteria ready."))

        if not Assessment.objects.exists():
            Assessment.objects.create(
                business_name="The Olive Garden Bistro",
                category=category,
                stage=Stage.INTAKE,
                business_user=users[Role.BUSINESS],
                assessor=users[Role.ASSESSOR],
                reviewer=users[Role.REVIEWER],
            )
            self.stdout.write(self.style.SUCCESS("Sample assessment created."))

        self.stdout.write(self.style.SUCCESS(
            "\nDemo logins:\n"
            "  admin / admin123        (full internal access + Django admin)\n"
            "  assessor / assessor123  (evidence + scoring)\n"
            "  reviewer / reviewer123  (peer review + senior approval)\n"
            "  business / business123  (business portal)\n"
        ))

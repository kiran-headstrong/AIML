from django.contrib import admin
from .models import (
    Profile, Category, Criterion, Assessment, Score,
    Evidence, PublishedReport, AuditLog,
)

admin.site.register(Profile)
admin.site.register(Category)
admin.site.register(Criterion)
admin.site.register(Assessment)
admin.site.register(Score)
admin.site.register(Evidence)
admin.site.register(PublishedReport)
admin.site.register(AuditLog)

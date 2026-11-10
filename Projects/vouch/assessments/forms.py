from django import forms
from django.contrib.auth.models import User

from .models import Assessment, Evidence, Role


class AssessmentCreateForm(forms.ModelForm):
    class Meta:
        model = Assessment
        fields = ["business_name", "category", "business_user", "assessor", "reviewer"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assessor"].queryset = User.objects.filter(profile__role=Role.ASSESSOR)
        self.fields["reviewer"].queryset = User.objects.filter(profile__role=Role.REVIEWER)
        self.fields["business_user"].queryset = User.objects.filter(profile__role=Role.BUSINESS)


class EvidenceForm(forms.ModelForm):
    class Meta:
        model = Evidence
        fields = ["evidence_type", "source", "file"]


class BusinessInfoForm(forms.ModelForm):
    class Meta:
        model = Assessment
        fields = ["business_info"]
        widgets = {"business_info": forms.Textarea(attrs={"rows": 6})}


class SummaryForm(forms.ModelForm):
    class Meta:
        model = Assessment
        fields = ["summary"]
        widgets = {"summary": forms.Textarea(attrs={"rows": 5})}

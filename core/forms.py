from django import forms
class YouTubeURLForm(forms.Form):
    url = forms.URLField(widget=forms.URLInput(attrs={"placeholder":"Paste YouTube video URL...","class":"form-control","required":True}))
class QuestionForm(forms.Form):
    question = forms.CharField(max_length=1500, widget=forms.Textarea(attrs={"placeholder":"Ask a question about this video...","class":"form-control","rows":2,"required":True}))

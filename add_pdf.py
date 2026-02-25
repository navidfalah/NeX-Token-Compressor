with open("dashboard/models.py", "r") as f:
    text = f.read()

text = text.replace("clean_content = models.TextField(help_text='The text of the document with placeholders inserted')", 
                    "clean_content = models.TextField(help_text='The text of the document with placeholders inserted')\n    redacted_file = models.FileField(upload_to='masked_docs/%Y/%m/', null=True, blank=True)")

with open("dashboard/models.py", "w") as f:
    f.write(text)

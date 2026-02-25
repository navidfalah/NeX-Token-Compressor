with open("dashboard/models.py", "r") as f:
    text = f.read()
text = text.replace("filename = models.CharField(max_length=255)", "filename = models.CharField(max_length=255)\n    file_size = models.BigIntegerField(default=0)")
with open("dashboard/models.py", "w") as f:
    f.write(text)

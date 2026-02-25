with open("templates/dashboard/masked_documents_list.html", "rb") as f:
    text = f.read()

idx = 0
while True:
    idx = text.find(b"document.filename", idx+1)
    if idx == -1: break
    snip = text[idx-10:idx+20]
    print("Found offset:", idx)
    print("SNIP:", snip)
    print("HEX:", snip.hex())

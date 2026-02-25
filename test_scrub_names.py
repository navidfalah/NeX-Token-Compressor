import scrubadub
scrubber = scrubadub.Scrubber()
scrubber.remove_detector('email')
scrubber.remove_detector('phone')
scrubber.remove_detector('url')
scrubber.remove_detector('credential')
scrubber.remove_detector('postalcode')
scrubber.remove_detector('ssn')
scrubber.remove_detector('twitter')
text = "Navid Falah is a Software Engineer at Circular Cities. Integration Web is great. 2024 and . 2025. Technische Leitung."
print("Scrubbed:", scrubber.clean(text))

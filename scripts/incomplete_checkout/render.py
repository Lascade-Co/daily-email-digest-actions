#!/usr/bin/env python3
"""Render the plain-text outreach email for incomplete checkout customers."""


def render():
    """Return (subject, body_text) for the outreach email."""
    subject = "Did you have trouble paying for Marine Radar?"
    body = (
        "Hi,\n"
        "\n"
        "I’m Angel Rose, Product Lead of MarineRadar. I noticed you tried "
        "to purchase credits from our website but the payment didn’t go through.\n"
        "\n"
        "I’d really appreciate if you could tell me what happened — was it:\n"
        "\n"
        "1. Your card didn’t work or was blocked by your bank?\n"
        "2. You needed a different payment method (PayPal, Google Pay, etc.)?\n"
        "3. Something else went wrong on the page?\n"
        "\n"
        "We’re working on adding more payment options and your feedback "
        "will directly help us fix this.\n"
        "\n"
        "If you’re still interested, just reply and I’ll make sure "
        "you get access.\n"
        "\n"
        "Thanks,\n"
        "Angel Rose\n"
        "Product Lead, MarineRadar"
    )
    return subject, body

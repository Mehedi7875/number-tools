#!/usr/bin/env python3
"""
number_info.py — Bangladesh-focused phone number info lookup.

Uses Google's libphonenumber (the `phonenumbers` Python port) for parsing,
validation, number type, timezone and region description, plus an explicit
Bangladesh mobile-prefix map for carrier detection (prefix allocation is the
most reliable public signal for BD numbers).

What this tool gives you: prefix/carrier metadata, format, validity, line
type, timezone. What it can NOT give you: the SIM owner's name or NID, and
the phone's live location. That data exists only with the mobile operators
and BTRC and is not available through any public tool or API.

Usage:
    python3 number_info.py 01712345678
    python3 number_info.py 01712345678 01912345678 +8801712345678
    python3 number_info.py            (interactive prompt)

Accepted input formats: 01XXXXXXXXX, 8801XXXXXXXXX, +8801XXXXXXXXX,
Dhaka landlines like 02-XXXXXXXX. Spaces and dashes are ignored.
"""

import sys

import phonenumbers
from phonenumbers import (
    PhoneNumberFormat,
    carrier as pn_carrier,
    geocoder as pn_geocoder,
    phonenumberutil,
    timezone as pn_timezone,
)

# ---------------------------------------------------------------------------
# Bangladesh mobile prefix map (BTRC prefix allocation).
# Primary carrier source for BD numbers: the first three digits of the
# national number (01X) identify the operator the number was allocated to.
# NOTE: with Mobile Number Portability (MNP) a subscriber can keep the number
# and move to another operator, so the *current* operator may differ.
# ---------------------------------------------------------------------------
BD_PREFIX_CARRIERS = {
    "013": "Grameenphone",
    "017": "Grameenphone",
    "014": "Banglalink",
    "019": "Banglalink",
    "018": "Robi",
    "016": "Airtel (Robi)",
    "015": "Teletalk",
    "011": "Citycell (defunct — network shut down)",
}

NUMBER_TYPE_NAMES = {
    phonenumberutil.PhoneNumberType.MOBILE: "Mobile",
    phonenumberutil.PhoneNumberType.FIXED_LINE: "Fixed line (landline)",
    phonenumberutil.PhoneNumberType.FIXED_LINE_OR_MOBILE: "Fixed line or mobile",
    phonenumberutil.PhoneNumberType.VOIP: "VoIP",
    phonenumberutil.PhoneNumberType.TOLL_FREE: "Toll-free",
    phonenumberutil.PhoneNumberType.PREMIUM_RATE: "Premium rate",
    phonenumberutil.PhoneNumberType.SHARED_COST: "Shared cost",
    phonenumberutil.PhoneNumberType.PERSONAL_NUMBER: "Personal number",
    phonenumberutil.PhoneNumberType.PAGER: "Pager",
    phonenumberutil.PhoneNumberType.UAN: "UAN",
    phonenumberutil.PhoneNumberType.VOICEMAIL: "Voicemail",
    phonenumberutil.PhoneNumberType.UNKNOWN: "Unknown",
}


def clean(raw: str) -> str:
    """Remove spaces, dashes and parentheses from user input."""
    return raw.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")


def bd_prefix(parsed) -> str | None:
    """Return the 01X prefix of a Bangladeshi number, or None."""
    if parsed.country_code != 880:
        return None
    nsn = str(parsed.national_number)  # significant digits, no trunk 0
    if nsn.startswith("1") and len(nsn) >= 3:
        return "0" + nsn[:2]
    return None


def lookup(raw: str) -> str:
    """Build a tidy text report for one raw number string."""
    lines = []
    lines.append("=" * 56)
    lines.append(f"Input: {raw}")

    cleaned = clean(raw)
    try:
        parsed = phonenumbers.parse(cleaned, "BD")
    except phonenumbers.NumberParseException as exc:
        lines.append("Result: INVALID — could not be parsed "
                     f"({exc.error_type.name if hasattr(exc, 'error_type') else exc})")
        lines.append("=" * 56)
        return "\n".join(lines)

    possible = phonenumbers.is_possible_number(parsed)
    valid = phonenumbers.is_valid_number(parsed)

    lines.append(f"E.164 format   : {phonenumbers.format_number(parsed, PhoneNumberFormat.E164)}")
    lines.append(f"International  : {phonenumbers.format_number(parsed, PhoneNumberFormat.INTERNATIONAL)}")
    lines.append(f"National       : {phonenumbers.format_number(parsed, PhoneNumberFormat.NATIONAL)}")
    lines.append(f"Possible       : {'yes' if possible else 'no'}")
    lines.append(f"Valid          : {'yes' if valid else 'NO — invalid number'}")

    ntype = phonenumberutil.number_type(parsed)
    lines.append(f"Number type    : {NUMBER_TYPE_NAMES.get(ntype, str(ntype))}")

    region = phonenumberutil.region_code_for_number(parsed) or "?"
    lines.append(f"Country/region : {region} (+{parsed.country_code})")

    try:
        zones = pn_timezone.time_zones_for_number(parsed)
        if zones:
            lines.append(f"Timezone(s)    : {', '.join(zones)}")
    except Exception:
        pass

    try:
        desc = pn_geocoder.description_for_number(parsed, "en")
        if desc:
            lines.append(f"Area (geocoder): {desc}")
    except Exception:
        pass

    # Carrier: explicit BD prefix map first (primary), library lookup second.
    prefix = bd_prefix(parsed)
    if prefix:
        mapped = BD_PREFIX_CARRIERS.get(prefix)
        if mapped:
            lines.append(f"Carrier (prefix {prefix}): {mapped}")
            lines.append("  ^ inferred from BTRC prefix allocation; with MNP "
                         "porting the actual current operator can differ.")
        else:
            lines.append(f"Carrier (prefix {prefix}): not allocated / unknown operator")
    try:
        lib_carrier = pn_carrier.name_for_number(parsed, "en")
        if lib_carrier:
            lines.append(f"Carrier (library) : {lib_carrier}")
    except Exception:
        pass

    if not valid:
        lines.append("Result: INVALID number (failed libphonenumber validation).")
    lines.append("=" * 56)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    numbers = argv[1:]
    if numbers:
        for raw in numbers:
            print(lookup(raw))
        return 0

    print("Bangladesh phone number info lookup.")
    print("Enter one number per line (blank line or Ctrl-D to quit).")
    while True:
        try:
            raw = input("Number: ")
        except EOFError:
            print()
            return 0
        if not raw.strip():
            return 0
        print(lookup(raw))


if __name__ == "__main__":
    sys.exit(main(sys.argv))

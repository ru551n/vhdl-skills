# Vendor Attribute and Primitive Policy

Prefer portable VHDL inference first.

Classify implementation choices as:
- `PORTABLE_VHDL`
- `VENDOR_ATTRIBUTE`
- `VENDOR_PRIMITIVE`
- `VENDOR_IP`

Prefer the least vendor-specific level that satisfies the requirement.

Use vendor attributes only when they provide a clear implementation benefit or
are required by the target architecture. Typical uses include RAM/ROM/DSP
inference, shift-register inference, synchronizer recognition, preservation,
placement guidance, and justified FSM encoding.

Rules:
- isolate attributes near the affected object
- document why they are needed
- verify exact vendor/family/tool syntax
- never use attributes merely to silence warnings
- prefer attributes over primitives when inference remains reliable

Use vendor primitives when portable inference cannot reliably express the
required hardware or exact device behavior matters. Wrap primitives behind a
project-local entity when practical.

Use vendor IP when it materially lowers implementation risk for complex
device-specific functionality. Do not choose vendor IP merely because it exists.

Whenever a design moves below `PORTABLE_VHDL`, report the portability class,
vendor/tool/family dependency, reason, expected benefit, and any portable fallback.

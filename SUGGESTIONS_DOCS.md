## POLICY.example.md

- "Where your document goes" — States "Neither is stored permanently by Leima" early on, but later documents that the email notary flow permanently stores sender address, recipient, and subject to Arweave. Should clearly mark the email notary as an exception to this rule.

## README.md

- Setup section — Uses `stamp@yourdomain.com` as a template (correct), but USECASES.md hardcodes `stamp@leima.fi` in examples. Readers may think they must use the leima.fi address.

## USECASES.md

- Email notary section — Hardcodes `stamp@leima.fi` as the example address. Should use a generic template like `stamp@yourdomain.com` to match README.md setup instructions.

## .env.example

- Line 7 — Uses "PoDe" as a comment but all other files use "POIDE". Should be standardised to "POIDE".

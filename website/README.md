# Endeavour Racing — Team Website

Official website for Endeavour Racing, a six-student team from Harrow School competing in the **STEM Racing Nationals 2026** (Development Class).

## Competition Results

| Award | Stage |
|---|---|
| 1st Place Overall — Regional Champions | Regionals |
| Best Engineered Car | Regionals |
| R&D Award Nomination | Regionals |
| Best Portfolios | Nationals |
| Sponsorships & Marketing Nomination | Nationals |

## Viewing the site

No build step needed — the entire site is a single self-contained HTML file.

```bash
# Just open it in any browser
open index.html        # macOS
start index.html       # Windows
xdg-open index.html   # Linux
```

Or double-click `index.html` in your file explorer.

## What the site includes

- **Hero** — team tagline and season stats
- **About** — who we are and what we compete in
- **Results** — all five awards and nominations with context
- **Story** — the reasoning behind the Endeavour name
- **Team** — individual profiles for each of the six members
- **Sponsors** — partner logos and a sponsorship enquiry form
- **Contact** — front-end contact form (demo) plus a direct mailto link

## Tech

Single-file HTML/CSS/JavaScript — no frameworks, no build tools, no dependencies. Fonts loaded from Google Fonts. The contact form is a front-end demo and does not send messages on its own; the working contact route is the team Instagram account linked in the footer. Wiring a live email endpoint would require the team's own email-service account and keys.

## Project context

Built as part of the team's sponsorship and marketing operation, which was nominated at the national stage for its professionalism. The site serves as the team's public face for sponsor outreach and brand identity.

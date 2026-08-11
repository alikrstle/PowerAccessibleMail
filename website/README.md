# Power Accessible Mail Website

The official bilingual website for Power Accessible Mail.

## Local development

```powershell
.\site.cmd setup
.\site.cmd serve
```

Open `http://localhost:4173`.

## Validation

```powershell
.\site.cmd test
```

The project validates the HTML, creates a production copy in `dist`, and runs
automated accessibility checks in desktop and mobile viewports. The release
check confirms that the saved download fallbacks match the latest release in
`alikrstle/PowerAccessibleMail`.

## Publishing

Build and publish the contents of `dist` as a static website. The intended
production domain is `https://soljan-alsharq.com`.

```powershell
.\site.cmd cloudflare-login
.\site.cmd pages
.\site.cmd deploy
```

The production Cloudflare Pages project is `power-accessible-mail`. It is a
Direct Upload project serving `soljan-alsharq.com` and
`www.soljan-alsharq.com`; publishing therefore runs through Wrangler.

The website source should live in its own GitHub repository. The application
repository remains the source for release metadata and downloadable assets;
`public/assets/downloads.js` reads its latest release through the GitHub API.

For deployment from GitHub, add `CLOUDFLARE_API_TOKEN` and
`CLOUDFLARE_ACCOUNT_ID` as Actions secrets. The `Deploy website` workflow is
manual and targets the protected `production` environment.

# Windows-installer laten ondertekenen (SignPath, gratis voor open source)

Zonder handtekening toont Windows *"Windows heeft uw pc beschermd"*. De
[SignPath Foundation](https://signpath.org/) ondertekent open-sourceprojecten gratis.
De workflow is al voorbereid; de ondertekenstap staat uit tot onderstaande stappen gedaan zijn.

## 1. Aanvragen

1. Ga naar <https://signpath.org/> en kies **Apply** voor het open-sourceprogramma.
2. Vul in:
   - Repository: `https://github.com/Svenvdp21/ha-desktop`
   - Licentie: MIT (OSI-goedgekeurd)
   - Build: GitHub Actions, workflow `.github/workflows/build.yml`
   - Wat ondertekend wordt: de Inno Setup-installer en `ha-desktop.exe` daarin
3. Zet tweestapsverificatie aan op je GitHub-account; dat is een voorwaarde.

SignPath beoordeelt de aanvraag zelf. Ze kunnen extra eisen stellen, bijvoorbeeld een
*code signing policy* op de projectpagina (zie stap 3).

## 2. Na goedkeuring: GitHub instellen

In SignPath maak je (of krijg je) een project met slug **`ha-desktop`** en een signing
policy met slug **`release-signing`**. Wijken die af, pas ze dan aan in de workflow.

Op GitHub, *Settings → Secrets and variables → Actions*:

| Soort | Naam | Waarde |
|---|---|---|
| Variable | `SIGNPATH_ORGANIZATION_ID` | je organisatie-ID uit SignPath |
| Secret | `SIGNPATH_API_TOKEN` | een API-token van een SignPath-gebruiker met submitter-rechten |

Vanaf de volgende release wordt de installer automatisch ondertekend.

## 3. Code signing policy (tekst voor de README, pas na goedkeuring)

> Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by
> [SignPath Foundation](https://signpath.org). Only the maintainer (Svenvdp21) can approve
> signing requests; releases are built from this repository by GitHub Actions. This program
> does not transfer any data to other networked systems unless the user configures a
> Home Assistant server.

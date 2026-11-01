# Eigen dnf-repo (GitHub Pages)

Alternatief voor COPR: een ondertekende dnf-repo op
<https://svenvdp21.github.io/ha-desktop/>, automatisch bijgewerkt na elke release
(workflow `.github/workflows/repo.yml`). Bevat de RPM van de nieuwste release (Fedora 44).

## Eenmalig instellen

1. **Sleutel als secret op GitHub zetten.** De privésleutel staat (alleen leesbaar voor jou) in
   `~/.config/ha-desktop-repo-signing.asc`:
   ```sh
   gh secret set REPO_GPG_PRIVATE_KEY --repo Svenvdp21/ha-desktop < ~/.config/ha-desktop-repo-signing.asc
   ```
   Bewaar dat bestand ook ergens veilig (bijv. een wachtwoordmanager). Kwijt = nieuwe sleutel
   maken, en alle gebruikers moeten dan de nieuwe sleutel accepteren.
2. **GitHub Pages aanzetten:** *Settings → Pages → Build and deployment → Source:*
   **GitHub Actions**. Of in de terminal:
   ```sh
   gh api -X POST repos/Svenvdp21/ha-desktop/pages -f build_type=workflow
   ```
3. **Eerste keer vullen:** *Actions → dnf repo → Run workflow*, of
   `gh workflow run repo.yml --repo Svenvdp21/ha-desktop`.

Daarna gaat het vanzelf bij elke release.

## Sleutel

Vingerafdruk: `8EA3 A1F2 1D6D 751D 4A4B  4E57 555E 1BD8 3947 0668` (RSA 4096, verloopt
oktober 2031). De publieke sleutel staat in `packaging/repo/ha-desktop.gpg`.

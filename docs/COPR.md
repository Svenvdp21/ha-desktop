# Fedora COPR

Met COPR kunnen Fedora-gebruikers de app installeren én automatisch updates krijgen via dnf.
De repo is er klaar voor: COPR bouwt rechtstreeks uit git met `.copr/Makefile`.

## Eenmalig instellen

1. Log in op <https://copr.fedorainfracloud.org/> met je Fedora-account (FAS).
2. **New Project**, naam `ha-desktop`. Kies de chroots, bijvoorbeeld `fedora-43-x86_64`,
   `fedora-44-x86_64` en `fedora-rawhide-x86_64`. Vink *Internet access during builds* aan
   (nodig om git te installeren als dat ontbreekt).
3. Tab **Packages → New package → SCM**:
   - Clone URL: `https://github.com/Svenvdp21/ha-desktop.git`
   - Committish: `main`
   - Spec file: `packaging/ha-desktop.spec`
   - SRPM build method: **make_srpm**
   - Vink *Auto-rebuild* aan.
4. Automatisch bouwen bij elke push: in COPR onder **Settings → Integrations** staat een
   GitHub-webhook-URL. Zet die op GitHub bij *Settings → Webhooks → Add webhook*
   (content type `application/json`, alleen *push*-events).

## Installeren (voor gebruikers)

```sh
sudo dnf copr enable <jouw-fas-naam>/ha-desktop
sudo dnf install ha-desktop
```

## Nieuwe versie

Verhoog `__version__` in `ha_desktop/__init__.py` én `Version:` in `packaging/ha-desktop.spec`,
en zet bovenaan de `%changelog` een regel voor die versie. De tests falen als die niet gelijk zijn.

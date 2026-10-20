%global app_id com.nordicnode.HADesktop

Name:           ha-desktop
Version:        %{app_version}
Release:        1%{?dist}
Summary:        Unofficial Home Assistant desktop app with notifications
# Code: MIT. Het meegeleverde logo is een merk van de Open Home Foundation
# (https://github.com/home-assistant/assets), alleen voor niet-commercieel gebruik.
License:        MIT
URL:            https://github.com/Svenvdp21/ha-desktop
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  desktop-file-utils

Requires:       python3-pyside6
Requires:       python3-gobject
Requires:       libsecret
Requires:       libnotify
Requires:       hicolor-icon-theme

%description
De Home Assistant-webinterface in een eigen venster, met eerste-keer-instellen,
systeemvak en bureaubladmeldingen via de Mobile App-integratie.

%prep
%autosetup

%build
# Pure Python; niets te bouwen.

%install
mkdir -p "%{buildroot}%{python3_sitelib}"
cp -a ha_desktop "%{buildroot}%{python3_sitelib}/"
find "%{buildroot}%{python3_sitelib}/ha_desktop" -name __pycache__ -prune -exec rm -rf {} +

install -Dm755 /dev/stdin "%{buildroot}%{_bindir}/ha-desktop" <<'EOF'
#!/usr/bin/python3 -sP
import sys
from ha_desktop.app import main
sys.exit(main(sys.argv))
EOF

install -Dm644 data/%{app_id}.desktop "%{buildroot}%{_datadir}/applications/%{app_id}.desktop"
install -Dm644 ha_desktop/data/%{app_id}.svg "%{buildroot}%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg"
install -Dm644 README.md "%{buildroot}%{_docdir}/%{name}/README.md"
install -Dm644 README.en.md "%{buildroot}%{_docdir}/%{name}/README.en.md"
install -Dm644 LICENSE "%{buildroot}%{_licensedir}/%{name}/LICENSE"

%check
desktop-file-validate "%{buildroot}%{_datadir}/applications/%{app_id}.desktop"

%files
%doc %{_docdir}/%{name}/README.md
%doc %{_docdir}/%{name}/README.en.md
%license %{_licensedir}/%{name}/LICENSE
%{_bindir}/ha-desktop
%{python3_sitelib}/ha_desktop/
%{_datadir}/applications/%{app_id}.desktop
%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg

%changelog
* Tue Oct 20 2026 Sven <nordicnode26@gmail.com> - 0.4.0-1
- Ook voor Windows, macOS, .deb en AppImage

* Tue Oct 20 2026 Sven <nordicnode26@gmail.com> - 0.3.0-1
- Nieuwe naam: Home Assistant Desktop (onofficieel); MIT-licentie

* Tue Oct 20 2026 Sven <nordicnode26@gmail.com> - 0.2.1-1
- Groter icoon (logo zonder extra marges)

* Tue Oct 20 2026 Sven <nordicnode26@gmail.com> - 0.2.0-1
- Engels en Nederlands; taal volgt het systeem

* Tue Oct 20 2026 Sven <nordicnode26@gmail.com> - 0.1.0-1
- Eerste versie

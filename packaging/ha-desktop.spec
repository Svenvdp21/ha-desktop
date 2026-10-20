%global app_id com.nordicnode.HADesktop

Name:           ha-desktop
Version:        %{app_version}
Release:        1%{?dist}
Summary:        Home Assistant-desktopapp met meldingen
# Eigen code voor privégebruik; het meegeleverde logo is een merk van de Open Home Foundation.
License:        LicenseRef-Proprietary
URL:            https://github.com/home-assistant/assets
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

%check
desktop-file-validate "%{buildroot}%{_datadir}/applications/%{app_id}.desktop"

%files
%doc %{_docdir}/%{name}/README.md
%{_bindir}/ha-desktop
%{python3_sitelib}/ha_desktop/
%{_datadir}/applications/%{app_id}.desktop
%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg

%changelog
* Tue Oct 20 2026 Sven <nordicnode26@gmail.com> - 0.1.0-1
- Eerste versie

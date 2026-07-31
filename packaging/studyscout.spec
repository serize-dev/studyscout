# RPM spec for STUDY//SCOUT — packages the PyInstaller-frozen binary.
# Built by packaging/build_rpm.sh (works on a Debian host with locally
# extracted rpm tools, or natively on Fedora).

Name:           studyscout
Version:        %{?scout_version}%{!?scout_version:1.0.0}
Release:        1%{?dist}
Summary:        STUDY//SCOUT — phosphor-green clinical-trials BD intel terminal
License:        MIT
URL:            https://localhost/studyscout
BuildArch:      x86_64

# The binary is frozen (bundles its own Python); don't scan or strip it.
AutoReqProv:    no
%global __os_install_post %{nil}
%global __spec_install_post %{nil}
%global debug_package %{nil}
%global __strip /bin/true
%global _build_id_links none

%description
A retro Neuromancer-style terminal app for clinical-trials business
development: hunts ClinicalTrials.gov for trials that fit your research
site, groups them into sponsor dossiers, drafts consolidated outreach
(Wintermute, Claude-powered), tracks the BD pipeline on a kanban, nags
about quiet relationships in a morning briefing, and works the
regulatory-startup checklist after a study is won.

%install
mkdir -p %{buildroot}%{_bindir} \
         %{buildroot}%{_docdir}/studyscout \
         %{buildroot}%{_datadir}/applications
install -m 0755 %{_sourcedir}/studyscout %{buildroot}%{_bindir}/studyscout
install -m 0644 %{_sourcedir}/README.md %{buildroot}%{_docdir}/studyscout/README.md
install -m 0644 %{_sourcedir}/HANDBOOK.md %{buildroot}%{_docdir}/studyscout/HANDBOOK.md
install -m 0644 %{_sourcedir}/studyscout.desktop \
    %{buildroot}%{_datadir}/applications/studyscout.desktop
for sz in 48 64 128 256; do
    mkdir -p %{buildroot}%{_datadir}/icons/hicolor/${sz}x${sz}/apps
    install -m 0644 %{_sourcedir}/studyscout_${sz}.png \
        %{buildroot}%{_datadir}/icons/hicolor/${sz}x${sz}/apps/studyscout.png
done

%post
touch --no-create %{_datadir}/icons/hicolor 2>/dev/null || :
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f %{_datadir}/icons/hicolor 2>/dev/null || :
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q %{_datadir}/applications 2>/dev/null || :
fi

%postun
touch --no-create %{_datadir}/icons/hicolor 2>/dev/null || :
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f %{_datadir}/icons/hicolor 2>/dev/null || :
fi

%files
%{_bindir}/studyscout
%doc %{_docdir}/studyscout/README.md
%doc %{_docdir}/studyscout/HANDBOOK.md
%{_datadir}/applications/studyscout.desktop
%{_datadir}/icons/hicolor/48x48/apps/studyscout.png
%{_datadir}/icons/hicolor/64x64/apps/studyscout.png
%{_datadir}/icons/hicolor/128x128/apps/studyscout.png
%{_datadir}/icons/hicolor/256x256/apps/studyscout.png

%changelog
* Fri Jul 03 2026 Arturo Serize <studyscout@localhost> - 1.0.0-1
- First packaged release: sponsor dossiers, robust sort, morning briefing,
  delta tracking, reg-handoff checklist, Fable-ready Wintermute.

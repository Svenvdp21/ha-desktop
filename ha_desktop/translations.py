"""Nederlandse vertalingen, per Engelse brontekst."""

NL = {
    # config
    "Enter the address of your Home Assistant server.": "Vul het adres van je Home Assistant-server in.",
    "The address must start with http:// or https://.": "Het adres moet met http:// of https:// beginnen.",
    "This doesn't look like a valid address.": "Dit lijkt geen geldig adres.",
    "The port number is invalid.": "Het poortnummer is ongeldig.",

    # haapi
    "Server not found. Check the address.": "Server niet gevonden. Controleer het adres.",
    "Connection refused. Is the port correct (usually 8123)?":
        "Verbinding geweigerd. Klopt de poort (meestal 8123)?",
    "The server is not responding (timeout).": "De server reageert niet (time-out).",
    "Secure connection failed.": "Beveiligde verbinding mislukt.",
    "Connection failed: {error}": "Verbinding mislukt: {error}",
    "This server's certificate is not trusted.": "Het certificaat van deze server wordt niet vertrouwd.",
    "A server responded, but it doesn't look like Home Assistant.":
        "Er reageert een server, maar het lijkt geen Home Assistant te zijn.",
    "The token is invalid or has expired.": "Het token is ongeldig of verlopen.",
    "The 'Mobile App' integration is not enabled in Home Assistant.":
        "De integratie 'Mobile App' is niet actief in Home Assistant.",
    "Registration failed (HTTP {status}).": "Registratie mislukt (HTTP {status}).",
    "Unexpected response from Home Assistant.": "Onverwacht antwoord van Home Assistant.",
    "Home Assistant refused the request: {error}": "Home Assistant weigerde het verzoek: {error}",

    # hasocket, push
    "Home Assistant rejected the token. Create a new token.":
        "Token geweigerd door Home Assistant. Maak een nieuw token aan.",
    "Subscribing to notifications failed: {error}. Turn notifications on again to register this device.":
        "Abonneren op meldingen mislukt: {error}. Schakel meldingen opnieuw in om dit apparaat te registreren.",
    "Connection lost; retrying in {delay} s.": "Verbinding verbroken; opnieuw proberen over {delay} s.",

    # quick
    "Quick controls…": "Snelbediening…",
    "Quick controls need an access token. Add one in Settings.":
        "Voor de snelbediening is een toegangstoken nodig. Voeg er een toe in Instellingen.",
    "Loading quick controls failed: {error}": "Snelbediening laden mislukt: {error}",
    "Couldn't control {name}: {error}": "Kon {name} niet bedienen: {error}",
    "unknown error": "onbekende fout",
    "Unavailable": "Niet beschikbaar",
    "Scene": "Scène",
    "Script": "Script",
    "Running": "Bezig",
    "Other": "Overig",

    # panel
    "Quick controls": "Snelbediening",
    "Quick controls — {app}": "Snelbediening — {app}",
    "On": "Aan",
    "Off": "Uit",
    "Drag sideways to dim": "Sleep opzij om te dimmen",
    "Close": "Sluiten",
    "Connecting…": "Verbinden…",
    "Not connected.": "Niet verbonden.",
    "Choose in Settings which lights, switches and scenes appear here.":
        "Kies in Instellingen welke lampen, schakelaars en scènes hier verschijnen.",
    "The chosen devices weren't found in Home Assistant.":
        "De gekozen apparaten zijn niet gevonden in Home Assistant.",

    # designer
    "Design quick controls — {app}": "Snelbediening ontwerpen — {app}",
    "Devices": "Apparaten",
    "Layout": "Indeling",
    "Name": "Naam",
    "Icon (mdi:…)": "Icoon (mdi:…)",
    "Drag to reorder. Double-click a name or icon to change it; icons are Material Design Icons "
    "like <code>mdi:sofa</code>, as in Home Assistant.":
        "Sleep om de volgorde te wijzigen. Dubbelklik op een naam of icoon om die aan te passen; "
        "iconen zijn Material Design Icons zoals <code>mdi:sofa</code>, net als in Home Assistant.",
    "Add section": "Sectie toevoegen",
    "Up": "Omhoog",
    "Down": "Omlaag",
    "Remove": "Verwijderen",
    "Arrange by area": "Indelen per ruimte",
    "One section per area in Home Assistant, with all lights, switches and scenes in it.":
        "Eén sectie per ruimte in Home Assistant, met alle lampen, schakelaars en scènes daarin.",
    "New section": "Nieuwe sectie",
    "(no heading)": "(zonder kop)",
    "Unknown icon": "Onbekend icoon",
    "Tick a device to add it to the selected section.":
        "Vink een apparaat aan om het aan de gekozen sectie toe te voegen.",
    "Replace your current layout with one section per area?":
        "Je huidige indeling vervangen door één sectie per ruimte?",
    "Loading areas…": "Ruimtes laden…",
    "Arranged by area. Remove what you don't need, or drag tiles around.":
        "Ingedeeld per ruimte. Verwijder wat je niet nodig hebt, of sleep tegels naar een andere plek.",

    # notifier
    "Open": "Openen",

    # webview
    "Settings…": "Instellingen…",
    "The server returned error code {code}.": "De server gaf foutcode {code}.",
    "Page crashed": "Pagina gecrasht",
    "The page crashed and will be reloaded.": "De weergave is vastgelopen en wordt opnieuw geladen.",

    # onboarding
    "Notifications use a <b>long-lived access token</b>. Create one in Home Assistant via "
    "<i>your profile → Security → Long-lived access tokens → Create token</i> (at the bottom "
    "of the page) and paste it below.":
        "Meldingen werken via een <b>long-lived access token</b>. Maak er een aan in Home "
        "Assistant via <i>je profiel → Beveiliging → Langdurige toegangstokens → Token "
        "aanmaken</i> (onderaan de pagina) en plak het hieronder.",
    "This computer then shows up in Home Assistant as a device, and you can send notifications "
    "with the action <code>notify.mobile_app_&lt;name&gt;</code>.":
        "Deze computer verschijnt daarna in Home Assistant als apparaat, en je kunt meldingen "
        "sturen met de actie <code>notify.mobile_app_&lt;naam&gt;</code>.",
    "Unknown certificate": "Onbekend certificaat",
    "The security certificate of <b>{host}</b> is not trusted (for example because it is "
    "self-signed).<br><br>Only trust it if this is your own server. Connect anyway?":
        "Het beveiligingscertificaat van <b>{host}</b> wordt niet vertrouwd (bijvoorbeeld "
        "omdat het zelf ondertekend is).<br><br>Vertrouw het alleen als dit je eigen server "
        "is. Toch verbinden?",
    "Paste your token here": "Plak hier je token",
    "Name of this computer": "Naam van deze computer",
    "Access token": "Toegangstoken",
    "Device name in Home Assistant": "Apparaatnaam in Home Assistant",
    "Enter a token first.": "Vul eerst een token in.",
    "Give this computer a name.": "Geef deze computer een naam.",
    "Connect": "Verbinden",
    "Welcome to {app}": "Welkom bij {app}",
    "Unofficial app, not affiliated with Home Assistant or the Open Home Foundation.":
        "Onofficiële app, niet verbonden aan Home Assistant of de Open Home Foundation.",
    "Enter the address of your Home Assistant server. This is usually "
    "<code>http://homeassistant.local:8123</code>, your server's IP address with port 8123, "
    "or your external address (e.g. Home Assistant Link).":
        "Vul het adres van je Home Assistant-server in. Dat is meestal "
        "<code>http://homeassistant.local:8123</code>, het IP-adres van je server met poort "
        "8123, of je externe adres (bijv. Home Assistant Link).",
    "Server address": "Serveradres",
    "Skip": "Overslaan",
    "Enable notifications": "Meldingen inschakelen",
    "Get notifications?": "Meldingen ontvangen?",
    "<i>No token yet? Choose Skip, log in first and turn on notifications later in "
    "Settings (Ctrl+,).</i>":
        "<i>Nog geen token? Kies Overslaan, log eerst in en zet meldingen later aan via "
        "Instellingen (Ctrl+,).</i>",

    # settings
    "● Connected — notifications are coming in": "● Verbonden — meldingen komen binnen",
    "● Connecting…": "● Verbinden…",
    "● Not connected": "● Niet verbonden",
    "● Error": "● Fout",
    "Settings — {app}": "Instellingen — {app}",
    "Server": "Server",
    "Change server…": "Andere server…",
    "Notifications": "Meldingen",
    "Show notifications from Home Assistant": "Meldingen van Home Assistant tonen",
    "Create token in Home Assistant…": "Token aanmaken in Home Assistant…",
    "A token is saved — leave empty to keep it": "Er is een token opgeslagen — laat leeg om te behouden",
    "Window": "Venster",
    "Keep running in the background when closed (system tray)":
        "Bij sluiten op de achtergrond blijven draaien (systeemvak)",
    "Your desktop has no system tray.": "Je bureaublad heeft geen systeemvak.",
    "Start at login (hidden)": "Starten bij inloggen (verborgen)",
    "Tiles like in Home Assistant for your lights, switches and scenes, right from the system tray.":
        "Tegels zoals in Home Assistant voor je lampen, schakelaars en scènes, direct vanuit het systeemvak.",
    "Tiles: {tiles} · Sections: {sections}": "Tegels: {tiles} · Secties: {sections}",
    "Nothing chosen yet.": "Nog niets gekozen.",
    "Design…": "Ontwerpen…",
    "Quick controls use the same access token as notifications; see <i>Notifications</i> in "
    "Settings for how to create one. Paste it here:":
        "De snelbediening gebruikt hetzelfde toegangstoken als de meldingen; onder "
        "<i>Meldingen</i> in Instellingen staat hoe je er een aanmaakt. Plak het hier:",
    "OK": "OK",
    "Load devices": "Apparaten laden",
    "Loading devices…": "Apparaten laden…",
    "Search…": "Zoeken…",
    "No lights, switches or scenes found in Home Assistant.":
        "Geen lampen, schakelaars of scènes gevonden in Home Assistant.",
    "Save": "Opslaan",
    "Cancel": "Annuleren",
    "Off.": "Uitgeschakeld.",
    "Not active yet — paste a token below and choose <b>Save</b>.":
        "Nog niet actief — plak hieronder een token en kies <b>Opslaan</b>.",
    "Change server": "Andere server",
    "Do you want to connect to a different Home Assistant server? You will go through the "
    "first-time setup again.":
        "Wil je verbinden met een andere Home Assistant-server? Je gaat dan opnieuw door de "
        "eerste-keer-instellingen.",

    # app
    "Try again now": "Nu opnieuw proberen",
    "Can't connect to Home Assistant": "Geen verbinding met Home Assistant",
    "Retrying automatically in {seconds} s…": "Automatisch opnieuw proberen over {seconds} s…",
    "Get Home Assistant notifications on this computer?":
        "Meldingen van Home Assistant op deze computer ontvangen?",
    "Set up…": "Instellen…",
    "Not now": "Niet nu",
    "{url} can't be reached.": "{url} is niet bereikbaar.",
    "Reload": "Herladen",
    "Quit": "Afsluiten",
    "notifications active": "meldingen actief",
    "notifications: error": "meldingen: fout",
    "connecting…": "verbinden…",
    "not connected": "niet verbonden",
    "start hidden in the system tray": "start verborgen in het systeemvak",
    "verbose logging": "uitgebreide logging",
}

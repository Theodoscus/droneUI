# shared.py
def open_homepage():
    from homepage import HomePage
    return HomePage()

def open_drone_control(field_path):
    from old.drone_control import DroneControlApp
    return DroneControlApp(field_path)

def open_report_gen(field_path):
    from report_gen import DroneReportApp
    return DroneReportApp(field_path)

def open_full_screen(field_path):
    from drone_control_fullscreen import DroneOperatingPage
    return DroneOperatingPage(field_path)

def open_real_drone_control(field_path):
    from real_drone_control import DroneControlApp
    return DroneControlApp(field_path)
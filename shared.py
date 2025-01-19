# shared.py
def open_homepage():
    from homepage import HomePage
    return HomePage()

def open_drone_control(field_path):
    from drone_control import DroneControlApp
    return DroneControlApp(field_path)

def open_report_gen(field_path):
    from report_gen import DroneReportApp
    return DroneReportApp(field_path)
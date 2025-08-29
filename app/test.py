from utils import update_project_info_company_D, get_project_info_instance_id


if __name__ == "__main__":
    form_instance_id = get_project_info_instance_id("25JZBTPFB157-1107")
    print("form_instance_id: ", form_instance_id)
    result = update_project_info_company_D("25JZBTPFB157-1107", "LEADERFIRM TECHNOLOGY COMPANY LIMITED", form_instance_id)
    print("result: ", result)
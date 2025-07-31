import subprocess


def _base_cmd(admin_name, admin_pass):
    return [
        "mosquitto_ctrl",
        "-h",
        "127.0.0.1",
        "-p",
        "1883",
        "-u",
        admin_name,
        "-P",
        admin_pass,
    ]


def add_client(admin_name, admin_pass, user, password, clientid=None):
    args = _base_cmd(admin_name, admin_pass) + [
        "dynsec",
        "createClient",
        user,
        "-p",
        password,
    ]
    if clientid:
        args += ["-i", clientid]
    process = subprocess.Popen(
        args,
        #        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    assert process.wait() == 0, f"Command {args} failed"


def add_role(admin_name, admin_pass, role_name):
    args = _base_cmd(admin_name, admin_pass) + [
        "dynsec",
        "createRole",
        role_name,
    ]
    process = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert process.wait() == 0, f"Command {args} failed"


def add_role_acl(admin_name, admin_pass, role_name, acltype, pattern, mode):
    assert acltype in {"subscribePattern", "publishClientReceive", "publishClientSend"}
    assert mode in {"allow", "deny"}

    args = _base_cmd(admin_name, admin_pass) + [
        "dynsec",
        "addRoleACL",
        role_name,
        acltype,
        pattern,
        mode,
        "99",
    ]
    # Make my rules the highest priority, like 99
    process = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert process.wait() == 0, f"Command {args} failed"


def add_client_role(admin_name, admin_pass, user, role_name):
    args = _base_cmd(admin_name, admin_pass) + [
        "dynsec",
        "addClientRole",
        user,
        role_name,
    ]
    process = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert process.wait() == 0, f"Command {args} failed"


def remove_client_role(admin_name, admin_pass, user, role_name):
    args = _base_cmd(admin_name, admin_pass) + [
        "dynsec",
        "removeClientRole",
        user,
        role_name,
    ]
    process = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert process.wait() == 0, f"Command {args} failed"

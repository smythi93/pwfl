import os


def fix_sanic(project, original_checkout):
    if project.project_name == "sanic":
        with open(
            os.path.join(original_checkout, "tests4py_requirements.txt"), "r"
        ) as f:
            content = f.read()
        with open(
            os.path.join(original_checkout, "tests4py_requirements.txt"), "w"
        ) as f:
            f.write(
                content.replace("requests-async==0.4.1", "http3==0.6.*\nrequests==2.*")
                .replace("requests-async==0.5.0", "http3==0.6.*\nrequests==2.*")
                .replace("chardet==2.3.0", "chardet==3.0.4")
            )
        if project.bug_id == 4:
            with open(os.path.join(original_checkout, "setup.py"), "r") as f:
                content = f.read()
            with open(os.path.join(original_checkout, "setup.py"), "w") as f:
                f.write(
                    content.replace(
                        '\n    "requests-async==0.5.0",',
                        '\n    "http3==0.6.*",\n    "requests==2.*",',
                    )
                )

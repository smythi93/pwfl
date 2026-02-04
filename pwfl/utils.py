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
            # copy sanic lib files to tests4py_venv/lib
            import shutil

            lib_path = os.path.join(original_checkout, "tests4py_venv", "lib")
            # find the python version folder
            python_version_folder = None
            for folder in os.listdir(lib_path):
                if folder.startswith("python"):
                    python_version_folder = folder
                    break
            if not python_version_folder:
                return
            site_packages_path = os.path.join(
                lib_path, python_version_folder, "site-packages"
            )
            # get sanic-libs path relative to __file__ parent
            sanic_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "external_libs",
                "sanic-libs",
            )
            for file in os.listdir(sanic_path):
                # copy tree if directory
                src_path = os.path.join(sanic_path, file)
                dst_path = os.path.join(site_packages_path, file)
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(src_path, dst_path)

import os
import os.path
import sys
import shutil


def html(ttfs):
    out = ""
    here = sys.path[0]
    dest_png_path = os.path.join(here, "png")
    try:
        os.mkdir(dest_png_path)
    except OSError:
        pass

    for pkg_name, png_paths in ttfs.items():
        png_pkg_path = os.path.join(dest_png_path, pkg_name)
        try:
            os.mkdir(png_pkg_path)
        except OSError:
            pass

        out += "<h3>{}</h3><p><ul>".format(pkg_name)
        for png_path in png_paths:
            shutil.copy(png_path, png_pkg_path)
            base_name = os.path.basename(png_path)
            out_str = '<li>{}<br><img src="{}"></li>'

            if False:  # local
                path = os.path.join(png_pkg_path, base_name)
                out_str = out_str.format(base_name, path)
            else:
                path = f"http://localhost:8000/png/{pkg_name}/{base_name}"
                out_str = out_str.format(base_name, path)

            out_str = out_str.format(base_name, path)
            out += out_str

        out += "</ul></p>"

    return out

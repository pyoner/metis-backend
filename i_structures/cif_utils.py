import tempfile  # FIXME remove as soon as pycodcif deals with the file in string
import re
#from io import StringIO

import numpy as np

from pycodcif import parse

from ase import Atom
from ase.spacegroup import crystal
from ase.geometry import cell_to_cellpar
#from ase.io import read as ase_read


def cif_to_ase(cif_string):
    """
    Naive pycodcif usage
    FIXME:
    as soon as pycodcif supports CIFs as strings,
    the tempfile below should be removed

    Args:
        cif_string: (str)

    Returns:
        ASE atoms (object) *or* None
        None *or* error (str)
    """

    # empty data_ keyword fixup
    for check in ["\ndata_\n", "\ndata_\r", "\rdata_\r"]:
        if check in cif_string:
            cif_string = cif_string.replace(check, check.replace("_", "_new"))
            break

    with tempfile.NamedTemporaryFile(suffix=".cif") as tmp:
        tmp.write(cif_string.encode("utf-8"))
        tmp.flush()

        try:
            parsed_cif = parse(tmp.name)[0][0]["values"]
        except:
            return None, "Invalid or non-standard CIF"

        if "_symmetry_int_tables_number" in parsed_cif:
            try:
                spacegroup = int(parsed_cif["_symmetry_int_tables_number"][0])
            except ValueError:
                return None, "Invalid space group info in CIF"

        elif "_symmetry_space_group_name_h-m" in parsed_cif:
            spacegroup = parsed_cif["_symmetry_space_group_name_h-m"][
                0
            ].strip()  # NB ase is very strict to whitespaces in HM symbols, so this is the most frequent error source
            if not spacegroup:
                return None, "Empty space group info in CIF"

        else:
            return None, "Absent space group info in CIF"

        try:
            cellpar = (
                float(parsed_cif["_cell_length_a"][0].split("(")[0]),
                float(parsed_cif["_cell_length_b"][0].split("(")[0]),
                float(parsed_cif["_cell_length_c"][0].split("(")[0]),
                float(parsed_cif["_cell_angle_alpha"][0].split("(")[0]),
                float(parsed_cif["_cell_angle_beta"][0].split("(")[0]),
                float(parsed_cif["_cell_angle_gamma"][0].split("(")[0]),
            )
            basis = np.transpose(
                np.array(
                    [
                        [
                            char.split("(")[0]
                            for char in parsed_cif["_atom_site_fract_x"]
                        ],
                        [
                            char.split("(")[0]
                            for char in parsed_cif["_atom_site_fract_y"]
                        ],
                        [
                            char.split("(")[0]
                            for char in parsed_cif["_atom_site_fract_z"]
                        ],
                    ]
                ).astype(np.float)
            )
            occupancies = [
                float(occ.split("(")[0])
                for occ in parsed_cif.get("_atom_site_occupancy", [])
            ]
        except:
            return None, "Unexpected non-numerical values occured in CIF"

    symbols = parsed_cif.get("_atom_site_type_symbol")

    if not symbols:
        symbols = parsed_cif.get("_atom_site_label")
        if not symbols:
            return None, "Cannot find atomic positions in CIF"

    non_els = re.compile(r"[^a-zA-Z]")
    symbols = [non_els.sub("", char) for char in symbols]

    occ_data = None
    if occupancies and any([occ != 1 for occ in occupancies]):
        basis = basis.tolist()
        partial_pos, occ_data = {}, {}
        for n in range(len(occupancies) - 1, -1, -1):
            if occupancies[n] != 1:
                disordered_pos = basis.pop(n)
                disordered_el = symbols.pop(n)
                partial_pos.setdefault(tuple(disordered_pos), {})[
                    disordered_el
                ] = occupancies[n]

        for xyz, occs in partial_pos.items():
            index = len(symbols)
            symbols.append(sorted(occs.keys())[0])
            basis.append(xyz)
            occ_data[index] = occs

    atom_data = []
    for n, xyz in enumerate(basis):
        try:
            atom_data.append(Atom(symbols[n], tuple(xyz), tag=n))
        except KeyError as exc:
            return None, "Unrecognized atom symbol: %s" % exc

    try:
        return (
            crystal(
                atom_data,
                spacegroup=spacegroup,
                cellpar=cellpar,
                primitive_cell=True,
                onduplicates="error",
                info=dict(disordered=occ_data) if occ_data else {},
            ),
            None,
        )
    except:
        return None, "Unrecognized sites or invalid site symmetry in CIF"

    #cif_file = StringIO(cif_string)
    #return ase_read(cif_file, format='cif', fractional_occupancies=True), None


def ase_to_eq_cif(ase_obj, supply_sg=True):
    """
    From ASE object generate CIF
    with symmetry-equivalent atoms;
    augment with the aux info, if needed
    """
    cif_data = "data_project_metis\n"

    parameters = cell_to_cellpar(ase_obj.cell)
    cif_data += "_cell_length_a    " + "%2.6f" % parameters[0] + "\n"
    cif_data += "_cell_length_b    " + "%2.6f" % parameters[1] + "\n"
    cif_data += "_cell_length_c    " + "%2.6f" % parameters[2] + "\n"
    cif_data += "_cell_angle_alpha " + "%2.6f" % parameters[3] + "\n"
    cif_data += "_cell_angle_beta  " + "%2.6f" % parameters[4] + "\n"
    cif_data += "_cell_angle_gamma " + "%2.6f" % parameters[5] + "\n"

    if supply_sg:
        sg_string = (
            "_symmetry_space_group_name_H-M '%s'\n_symmetry_Int_Tables_number %s\n"
            % (
                getattr(ase_obj.info.get("spacegroup", object), "symbol", "P1"),
                getattr(ase_obj.info.get("spacegroup", object), "no", 1),
            )
        )
    else:
        sg_string = (
            "_symmetry_space_group_name_H-M 'P1'\n_symmetry_Int_Tables_number 1\n"
        )

    cif_data += sg_string
    cif_data += "\nloop_" + "\n"
    cif_data += " _symmetry_equiv_pos_as_xyz" + "\n"
    cif_data += " +x,+y,+z" + "\n"

    cif_data += "\nloop_" + "\n"
    cif_data += " _atom_site_type_symbol" + "\n"
    cif_data += " _atom_site_fract_x" + "\n"
    cif_data += " _atom_site_fract_y" + "\n"
    cif_data += " _atom_site_fract_z" + "\n"

    pos = ase_obj.get_scaled_positions(wrap=False)
    for n, item in enumerate(ase_obj):
        cif_data += " {:3s} {: 6.3f} {: 6.3f} {: 6.3f}\n".format(
            item.symbol, pos[n][0], pos[n][1], pos[n][2]
        )

    return cif_data


import random
import json

from flask import Blueprint, current_app, request, Response

from mpds_ml_labs.struct_utils import detect_format, poscar_to_ase, optimade_to_ase, refine, get_formula
from mpds_ml_labs.cif_utils import cif_to_ase

from utils import SECRET, fmt_msg, is_plain_text, html_formula, is_valid_uuid, ase_serialize
from i_data import Data_Storage


bp_data = Blueprint('data', __name__, url_prefix='/data')


@bp_data.route("/create", methods=['POST'])
def create():
    """
    Data item recognition and saving logics
    Expects
        secret: string
        content: string
    Returns
        JSON->error: string
        or confirmation object
        {object->uuid, object->type, object->name}
    """
    secret = request.values.get('secret')
    if secret != SECRET:
        return fmt_msg('Unauthorized', 401)

    content = request.values.get('content')
    if not content:
        return fmt_msg('Empty request')

    if not 0 < len(content) < 200000:
        return fmt_msg('Request size is invalid')

    if not is_plain_text(content):
        return fmt_msg('Request contains unsupported (non-latin) characters')

    fmt = detect_format(content)

    if fmt == 'cif':
        ase_obj, error = cif_to_ase(content)

    elif fmt == 'poscar':
        ase_obj, error = poscar_to_ase(content)

    elif fmt == 'optimade':
        ase_obj, error = optimade_to_ase(content)

    else: return fmt_msg('Provided data format unsuitable or not recognized')

    if error: return fmt_msg(error)

    if 'disordered' in ase_obj.info:
        return fmt_msg('Structural disorder is not supported')

    ase_obj, error = refine(ase_obj, conventional_cell=True)
    if error:
        return fmt_msg(error)

    formula = get_formula(ase_obj)
    content = ase_serialize(ase_obj)

    db = Data_Storage()
    uuid = db.put_item(formula, content, 0)
    db.close()

    return Response(json.dumps(dict(
        uuid=uuid,
        type=0,
        name=html_formula(formula),
    ), indent=4), content_type='application/json', status=200)


@bp_data.route("/listing", methods=['POST'])
def listing():
    """
    Expects
        secret: string
        uuid: uuid or uuid[]
    Returns
        JSON->error: string
        or listing
        [ {object->uuid, object->type, object->name}, ... ]
    """
    secret = request.values.get('secret')
    if secret != SECRET:
        return fmt_msg('Unauthorized', 401)

    uuid = request.values.get('uuid')
    current_app.logger.warning(uuid)
    if not uuid:
        return fmt_msg('Empty request')

    db = Data_Storage()

    if ':' in uuid:
        uuids = set( uuid.split(':') )
        for uuid in uuids:
            if not is_valid_uuid(uuid): return fmt_msg('Invalid request')

        items = db.get_items(list(uuids))

        found_uuids = set( [item['uuid'] for item in items] )
        if found_uuids != uuids:
            return fmt_msg('No such content', 204)

    else:
        if not is_valid_uuid(uuid): return fmt_msg('Invalid request')

        item = db.get_item(uuid)
        items = [item] if item else []

        if not items: return fmt_msg('No such content', 204)

    db.close()

    items = [dict(uuid=item['uuid'], name=html_formula(item['label']), type=item['type']) for item in items]
    return Response(json.dumps(items, indent=4), content_type='application/json', status=200)


@bp_data.route("/delete", methods=['POST'])
def delete():
    """
    Expects
        secret: string
        uuid: uuid
    Returns
        JSON->error: string
        or JSON empty dict
    """
    secret = request.values.get('secret')
    if secret != SECRET:
        return fmt_msg('Unauthorized', 401)

    uuid = request.values.get('uuid')
    if not uuid or not is_valid_uuid(uuid):
        return fmt_msg('Empty or invalid request')

    db = Data_Storage()
    result = db.drop_item(uuid)
    db.close()

    if result:
        return Response('{}', content_type='application/json', status=200)
    return fmt_msg('No such content', 204)
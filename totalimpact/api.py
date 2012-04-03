from flask import Flask, jsonify, json, request, redirect, abort, make_response
from flask import render_template, flash
from flaskext.login import login_user, current_user
import json, time

from totalimpact.core import app, login_manager
from totalimpact.config import Configuration
from totalimpact import dao
#from totalimpact.backend import TotalImpactBackend
from totalimpact.models import Item, Collection, User
from totalimpact.providers.provider import ProviderFactory, ProviderConfigurationError
from totalimpact import util
from totalimpact.tilogging import logging


logger = logging.getLogger(__name__)

# FIXME this should go somewhere better?
config = Configuration()
providers = ProviderFactory.get_providers(config)

mydao = dao.Dao(config)


# do account / auth stuff
@login_manager.user_loader
def load_account_for_login_manager(userid):
    out = User.get(userid)
    return out

@app.context_processor
def set_current_user():
    """ Set some template context globals. """
    return dict(current_user=current_user)

@app.before_request
def standard_authentication():
    """Check remote_user on a per-request basis."""
    remote_user = request.headers.get('REMOTE_USER', '')
    if remote_user:
        user = User.get(remote_user)
        if user:
            login_user(user, remember=False)
    elif 'api_key' in request.values:
        res = User.query(q='api_key:"' + request.values['api_key'] + '"')['hits']['hits']
        if len(res) == 1:
            user = User.get(res[0]['_source']['id'])
            if user:
                login_user(user, remember=False)

@app.before_request
def connect_to_db():
    try:

        ## FIXME add a check to to make sure it has views already.  If not, reset
        #mydao.delete_db(db_name)

        if not mydao.db_exists(app.config["DB_NAME"]):
            mydao.create_db(app.config["DB_NAME"])
        mydao.connect_db(app.config["DB_NAME"])
    except LookupError:
        print "CANNOT CONNECT TO DATABASE, maybe doesn't exist?"
        raise LookupError


# <path:> converter for flask accepts slashes.  Useful for DOIs.
@app.route('/tiid/<ns>/<path:nid>', methods=['GET'])
def tiid(ns, nid):
    # Nothing in the database, so return error for everything now
    # FIXME needs to look things up
    abort(404)


@app.route('/item/<namespace>/<path:nid>', methods=['POST', 'GET'])
def item_namespace_post(namespace, nid):
    now = time.time()
    item = Item(mydao)
    item.aliases = {}
    item.aliases["namespace"] = nid
    item.created = now
    item.last_modified = now

    ## FIXME
    ## Should look up this namespace and id and see if we already have a tiid
    ## If so, return its tiid with a 200.
    # right now this makes a new item every time, creating many dups

    # FIXME pull this from Aliases somehow?
    # check to make sure we know this namespace
    #known_namespace = namespace in Aliases().get_valid_namespaces() #implement
    known_namespaces = ["DOI"]  # hack in the meantime
    if not namespace in known_namespaces:
        abort(501) # "Not Implemented"

    # otherwise, save the item
    item.save() 
    response_code = 201 # Created

    tiid = item.id

    if not tiid:
        abort(500)
    resp = make_response(json.dumps(tiid), response_code)        
    resp.mimetype = "application/json"
    return resp


@app.route('/item/<tiids>', methods=['GET'])
@app.route('/items/<tiids>', methods=['GET'])
def items(tiids):
    items = []
    for index,tiid in enumerate(tiids.split(',')):
        if index > 99: break    # weak
        try:
            item = Item(mydao, id=tiid)
            item.load()
            items.append( item.as_dict() )
        except LookupError:
            # TODO: is it worth setting this blank? or do nothing?
            # if do nothing, returned list will not match supplied list
            items.append( {} )

    if len(items) == 1 and not request.path.startswith('/items/') :
        items = items[0]

    if items:
        resp = make_response( json.dumps(items, sort_keys=True, indent=4) )
        resp.mimetype = "application/json"
        return resp
    else:
        abort(404)


        
# routes for providers (TI apps to get metrics from remote sources)
# external APIs should go to /item routes
# should return list of member ID {namespace:id} k/v pairs
# if > 100 memberitems, return 100 and response code indicates truncated
# examples:
#    /provider/GitHub/memberitems?query=jasonpriem&type=profile
#    /provider/GitHub/memberitems?query=bioperl&type=orgs
#    /provider/Dryad/memberitems?query=Otto%2C%20Sarah%20P.&type=author
@app.route('/provider/<pid>/memberitems', methods=['GET'])
def provider_memberitems(pid):
    query = request.values.get('query','')
    qtype = request.values.get('type','')

    logger.debug("In provider_memberitems with " + query + " " + qtype)
    
    # TODO: where does providers list come from now? used to be from config, but not certain now.    
    for prov in providers:
        if prov.id == pid:
            provider = prov
            break

    logger.debug("provider: " + prov.id)

    memberitems = provider.member_items(query, qtype)
    
    resp = make_response( json.dumps(memberitems, sort_keys=True, indent=4), 200 )
    resp.mimetype = "application/json"
    return resp

# For internal use only.  Useful for testing before end-to-end working
# Example: http://127.0.0.1:5000/provider/Dryad/aliases/10.5061%25dryad.7898
@app.route('/provider/<pid>/aliases/<id>', methods=['GET'] )
def provider_aliases(pid,id):

    # TODO: where does this come from now? used to be from config, but not certain now.
    for prov in providers:
        if prov.id == pid:
            provider = prov
            break

    aliases = provider.get_aliases_for_id(id.replace("%", "/"))

    resp = make_response( json.dumps(aliases, sort_keys=True, indent=4) )
    resp.mimetype = "application/json"
    return resp

# For internal use only.  Useful for testing before end-to-end working
# Example: http://127.0.0.1:5000/provider/Dryad/metrics/10.5061%25dryad.7898
@app.route('/provider/<pid>/metrics/<id>', methods=['GET'] )
def provider_metrics(pid,id):

    # TODO: where does this come from now? used to be from config, but not certain now.
    for prov in providers:
        if prov.id == pid:
            provider = prov
            break

    metrics = provider.get_metrics_for_id(id.replace("%", "/"))

    resp = make_response( json.dumps(metrics.data, sort_keys=True, indent=4) )
    resp.mimetype = "application/json"
    return resp

# For internal use only.  Useful for testing before end-to-end working
# Example: http://127.0.0.1:5000/provider/Dryad/biblio/10.5061%25dryad.7898
@app.route('/provider/<pid>/biblio/<id>', methods=['GET'] )
def provider_biblio(pid,id):

    # TODO: where does this come from now? used to be from config, but not certain now.
    for prov in providers:
        if prov.id == pid:
            provider = prov
            break

    biblio = provider.get_biblio_for_id(id.replace("%", "/"))

    resp = make_response( json.dumps(biblio.data, sort_keys=True, indent=4) )
    resp.mimetype = "application/json"
    return resp

# routes for collections 
# (groups of TI scholarly object items that are batched together for scoring)
@app.route('/collection', methods = ['GET','POST','PUT','DELETE'])
@app.route('/collection/<cid>/<tiid>')
def collection(cid='',tiid=''):
    try:
        coll = Collection(mydao, id=cid)
        coll.load()
    except:
        coll = False
    
    if request.method == "POST":
        if coll:
            if tiid:
                # TODO: update the list of tiids on this coll with this new one
                coll.save()
            else:
                # TODO: merge the payload (a collection object) with the coll we already have
                # use richards merge stuff to merge hierarchically?
                coll.save()
        else:
            if tiid:
                abort(404) # nothing to update
            else:
                # TODO: if save fails here, we just pass error to the user - should prob update this
                coll = Collection(mydao, seed = request.json )
                coll.save() # making a new collection

    elif request.method == "PUT":
        coll = Collection(mydao, seed = request.json )
        coll.save()

    elif request.method == "DELETE":
        if coll:
            if tiid:
                # TODO: remove tiid from tiid list on coll
                coll.save()
            else:
                coll.delete()
                abort(404)

    try:
        resp = make_response( json.dumps( coll.as_dict() ) )
        resp.mimetype = "application/json"
        return resp
    except:
        abort(404)


# routes for user stuff
@app.route('/user/<uid>', methods = ['GET','POST','PUT','DELETE'])
def user(uid=''):
    try:
        user = User(mydao, id=uid)
        user.load()
    except:
        user = False

    # POST updated user data (but don't accept changes to the user colls list)    
    if request.json:
        newdata = request.json
        if 'collection_ids' in newdata:
            del newdata['collection_ids']
        if 'password' in newdata:
            pass # should prob hash the password here (fix once user accounts exist)
        # TODO: update this user with the new info, however that is done now
        if not user:
            user = User(mydao, seed = newdata )
        user.save()
    
    # kill this user
    if request.method == 'DELETE' and user:
        user.delete()
        abort(404)

    try:
        resp = make_response( json.dumps(user.as_dict(), sort_keys=True, indent=4) )
        resp.mimetype = "application/json"
        return resp
    except:
        abort(404)


if __name__ == "__main__":

    # i think that maybe we want to start the watcher seperately?
    # watcher = TotalImpactBackend(Configuration())

    # run it
    app.run(host='0.0.0.0', debug=True)


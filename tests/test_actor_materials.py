import copy
import hashlib
import io
import json
from types import SimpleNamespace as NS
import pytest
from PIL import Image
from carla_safety_agent.actor_materials import actor_material_edits
from carla_safety_agent.material_library import MaterialLibrary,MaterialTransaction
from carla_safety_agent.scene_store import SceneStore,validate_scene
from carla_safety_agent.project_bundle import export_bundle,read_bundle,import_bundle
from test_studio_bridge import functions


def fixture(model='vehicle.audi.a2'):
    from carla_safety_agent.actor_materials import SUPPORTED
    obj={'stable_id':'vehicle','blueprint_id':'vehicle.audi.a2',
         'transform':{'location':{'x':0,'y':0,'z':1},'rotation':{'pitch':0,'yaw':0,'roll':0}}}
    material={'stable_id':'vehicle','blueprint_id':'vehicle.audi.a2','component':'VehicleMesh','slot':4,'texture':'a'*64}
    obj['blueprint_id']=model
    material.update(blueprint_id=model,component=SUPPORTED[model][0],slot=SUPPORTED[model][1])
    return {'map':'Town04','objects':[obj],'actor_materials':[material]}


@pytest.mark.parametrize('damage',['missing_actor','model','slot','component','bool','hash','duplicate','extra'])
def test_bad_actor_reference_rejected_before_scene_save(damage,tmp_path):
    doc=fixture();record=doc['actor_materials'][0]
    if damage=='missing_actor':doc['objects']=[]
    if damage=='model':record['blueprint_id']='walker.pedestrian.0001'
    if damage=='slot':record['slot']=5
    if damage=='component':record['component']='OtherMesh'
    if damage=='bool':record['slot']=True
    if damage=='hash':record['texture']='../file'
    if damage=='duplicate':doc['actor_materials'].append(copy.deepcopy(record))
    if damage=='extra':record['source_path']='/tmp/secret'
    with pytest.raises(ValueError):SceneStore(tmp_path).save(doc,'bad')
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('model',['vehicle.audi.a2','walker.pedestrian.0001'])
def test_actor_texture_roundtrip_copies_referenced_bytes_only(tmp_path,model):
    doc=fixture(model);texture=b'fixture';digest=hashlib.sha256(texture).hexdigest()
    doc['actor_materials'][0]['texture']=digest
    store=SceneStore(tmp_path/'data/scenes');saved=store.save(doc,'painted')
    folder=tmp_path/'data/textures';folder.mkdir();(folder/(digest+'.png')).write_bytes(texture)
    archive=tmp_path/'scene.zip';manifest=export_bundle(store.root,tmp_path/'data',[saved['head']['scene_id']],archive)
    assert manifest['dependencies']['actor_material_slots']==[[model,doc['actor_materials'][0]['component'],doc['actor_materials'][0]['slot']]]
    imported=import_bundle(archive,tmp_path)
    assert (imported/'data/textures'/(digest+'.png')).read_bytes()==texture
    assert SceneStore(imported/'data/scenes').read(saved['head']['scene_id'])==saved
    del doc['actor_materials']
    legacy=store.save(doc,'legacy');old=tmp_path/'old.zip'
    manifest=export_bundle(store.root,tmp_path/'data',[legacy['head']['scene_id']],old)
    assert 'actor_material_slots' not in manifest['dependencies']
    assert set(read_bundle(old)[1])=={'scenes/'+legacy['head']['scene_id']+'/'+name for name in ('head.json',legacy['head']['version']+'.json')}


@pytest.mark.parametrize('mode',['replace','clear','corrupt','bind_failure'])
@pytest.mark.parametrize('model',['vehicle.audi.a2','walker.pedestrian.0001'])
def test_actor_transaction_scopes_to_selected_stable_id_and_compensates(tmp_path,mode,model):
    doc=fixture(model);library=MaterialLibrary(tmp_path)
    def texture(color):
        out=io.BytesIO();Image.new('RGB',(2,2),color).save(out,format='PNG');return library.put_texture(out.getvalue())
    before,desired=texture('red'),texture('blue');doc['actor_materials'][0]['texture']=desired
    old={**doc['actor_materials'][0],'texture':before}
    actor=NS(id=7,type_id=model)
    records={'7':{'stable_id':'vehicle','origin':'user','type_id':actor.type_id,'actor_materials':[old]},
             '8':{'stable_id':'unrelated','origin':'user','type_id':actor.type_id,'actor_materials':[{'do_not_touch':True}]}}
    calls=[]
    failures=[mode=='bind_failure']
    def bind(episode,actor,stable,**metadata):
        if failures[0]:
            failures[0]=False
            raise OSError('controlled metadata failure')
        records[str(actor.id)].update(metadata)
    world=NS(id=10,apply_color_texture_to_object=lambda target,param,texture:calls.append(target))
    env=functions('prepare_scene_actor_materials',_provenance=NS(records=lambda _:records,bind=bind),
        runtime_name_for_actor=lambda *_:'ExactVehicle',MATERIALS=library,MaterialTransaction=MaterialTransaction,
        Image=Image,io=io,decode_texture=lambda payload,size:(None,payload),
        carla=NS(MaterialParameter=NS(Diffuse=1),TextureColor=lambda *_:'restore'))
    if mode=='corrupt':
        (tmp_path/'textures'/(desired+'.png')).write_bytes(b'corrupted')
        with pytest.raises(ValueError,match='checksum'):
            env['prepare_scene_actor_materials'](world,doc,{'vehicle':actor},records)
        assert not calls and records['7']['actor_materials']==[old]
        return
    if mode=='clear':doc['actor_materials']=[]
    txn=env['prepare_scene_actor_materials'](world,doc,{'vehicle':actor},records)
    assert not calls
    if mode=='bind_failure':
        with pytest.raises(OSError,match='metadata'):txn.apply()
    else:
        txn.apply();assert records['7']['actor_materials']==doc['actor_materials']
    txn.rollback();assert records['7']['actor_materials']==[old]
    assert records['8']['actor_materials']==[{'do_not_touch':True}]
    prefix=f"ExactVehicle|csa|{old['component']}|{old['slot']}|"
    assert calls==[prefix+('restore' if mode=='clear' else 'apply'),prefix+'apply']


def test_actor_material_validation_preserves_legacy_absence():
    doc=fixture();assert validate_scene(doc)=={**doc,'schema_version':'carla-scene/1'}
    doc.pop('actor_materials');assert 'actor_materials' not in validate_scene(doc)


def test_shared_texture_digest_keeps_each_actor_resolution(tmp_path):
    car=fixture();walker=fixture('walker.pedestrian.0001')
    walker['objects'][0]['stable_id']='walker'
    walker['actor_materials'][0]['stable_id']='walker'
    doc={'objects':car['objects']+walker['objects'],'actor_materials':car['actor_materials']+walker['actor_materials']}
    library=MaterialLibrary(tmp_path);image=io.BytesIO();Image.new('RGB',(2,2),'red').save(image,format='PNG')
    digest=library.put_texture(image.getvalue())
    live={};records={}
    for number,obj in enumerate(doc['objects'],1):
        actor=NS(id=number,type_id=obj['blueprint_id']);live[obj['stable_id']]=actor
        records[str(number)]={'stable_id':obj['stable_id'],'type_id':actor.type_id,'origin':'user'}
    for record in doc['actor_materials']:record['texture']=digest
    sizes=[]
    def decode(payload,size):sizes.append(size);return None,size
    world=NS(id=10,apply_color_texture_to_object=lambda *_:None)
    env=functions('prepare_scene_actor_materials',_provenance=NS(records=lambda _:records,bind=lambda *_args,**_kw:None),
        runtime_name_for_actor=lambda _world,actor:str(actor.id),MATERIALS=library,MaterialTransaction=MaterialTransaction,
        Image=Image,io=io,decode_texture=decode,carla=NS(MaterialParameter=NS(Diffuse=1)))
    env['prepare_scene_actor_materials'](world,doc,live,records).apply()
    assert sorted(sizes)==[(1024,1024),(2048,2048)]

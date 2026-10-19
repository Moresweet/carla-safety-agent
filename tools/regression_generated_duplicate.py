"""Verify generated-mesh duplication without changing existing scene objects."""
import json
import uuid
from regression_scene_versions import ROOT, request
from cleanup_superseded_model_captures import idle


def main():
    import carla
    idle()
    assert request('system/preflight')['ready']
    output=ROOT/'runs/validation'/('generated-duplicate-'+uuid.uuid4().hex+'.json')
    report={'passed':False};owned=set()
    try:
        source=request('objects/spawn',{'blueprint_id':'generated.prop.csa_safetybarrier',
            'transform':{'location':{'x':393.098,'y':-228.088,'z':2.5},'scale':37,'mass':0}})['object']
        owned.add(source['id'])
        copied=request('objects/duplicate',{'actor_id':source['id']})['object']
        owned.add(copied['id'])
        assert source['id']!=copied['id']
        client=carla.Client('127.0.0.1',2000);client.set_timeout(5)
        world=client.get_world();world.wait_for_tick(5)
        actors=[world.get_actor(i) for i in (source['id'],copied['id'])]
        assert all(actor and actor.type_id=='static.prop.mesh' for actor in actors)
        attributes=[dict(actor.attributes) for actor in actors]
        for key in ('mesh_path','scale','scale_x','scale_y','scale_z','mass'):
            assert attributes[0][key]==attributes[1][key],key
        assert float(attributes[1]['scale'])==37 and float(attributes[1]['mass'])==0
        assert all(abs(getattr(actors[0].bounding_box.extent,k)-getattr(actors[1].bounding_box.extent,k))<.001 for k in ('x','y','z'))
        doc=request('scenes/save',{'name':'验收：生成物体复制参数'})['document']
        rows=[row for row in doc['objects'] if row['blueprint_id']=='generated.prop.csa_safetybarrier'
              and row.get('spawn_options')=={'mass':0.0,'scale':37.0}]
        assert len(rows)==2 and len({row['stable_id'] for row in rows})==2
        report.update(passed=True,source=source,copied=copied,attributes=attributes,objects=rows)
    finally:
        report['cleanup']=[]
        for actor_id in owned:
            try:report['cleanup'].append(request('objects/delete',{'actor_id':actor_id}))
            except Exception as error:
                report['passed']=False
                report['cleanup'].append({'actor_id':actor_id,'error':str(error)})
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({'receipt':str(output),'passed':report['passed']}))
    if not report['passed']:raise RuntimeError('Duplicate acceptance or cleanup failed')


if __name__=='__main__':main()

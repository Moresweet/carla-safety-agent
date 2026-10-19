"""One-shot native projection process. Never connects to a simulator."""
import json
import sys
from .map_projection_archive import read_map_projection
from .projected_prediction import project_driveadapter_prediction


def main():
    request=json.loads(sys.stdin.read(4*1024**2))
    ref=request['reference']
    xml=read_map_projection(request['root'],ref)
    import carla
    road=carla.Map(ref['map_name'],xml)
    def convert(lat,lon):
        point=road.geolocation_to_transform(carla.GeoLocation(latitude=lat,longitude=lon,altitude=0))
        return [point.x,point.y]
    result=project_driveadapter_prediction(request['metadata'],request['pose'],convert)
    result['map_sha256']=ref['sha256']
    print(json.dumps(result,allow_nan=False))


if __name__=='__main__':main()

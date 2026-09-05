#define mLefttChild mLeftChild
#include <fbxsdk.h>

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

struct Vertex { double x, y, z, u, v; };

int main(int argc, char **argv) {
  if (argc != 4 && argc != 5) {
    std::cerr << "usage: fbx_mesh_to_json input.fbx output.json material-slot [node-name-suffix]\n";
    return 2;
  }
  const int wanted_material = std::stoi(argv[3]);
  const std::string wanted_suffix = argc == 5 ? argv[4] : "";
  FbxManager *manager = FbxManager::Create();
  FbxIOSettings *settings = FbxIOSettings::Create(manager, IOSROOT);
  manager->SetIOSettings(settings);
  FbxImporter *importer = FbxImporter::Create(manager, "");
  if (!importer->Initialize(argv[1], -1, manager->GetIOSettings())) {
    std::cerr << importer->GetStatus().GetErrorString() << '\n';
    return 1;
  }
  FbxScene *scene = FbxScene::Create(manager, "scene");
  importer->Import(scene);
  importer->Destroy();

  std::vector<Vertex> vertices;
  std::vector<FbxNode *> stack{scene->GetRootNode()};
  while (!stack.empty()) {
    FbxNode *node = stack.back(); stack.pop_back();
    for (int i = 0; i < node->GetChildCount(); ++i) stack.push_back(node->GetChild(i));
    FbxMesh *mesh = node->GetMesh();
    if (!mesh) continue;
    const std::string node_name = node->GetName();
    if (!wanted_suffix.empty() &&
        (node_name.size() < wanted_suffix.size() ||
         node_name.compare(node_name.size() - wanted_suffix.size(),
                           wanted_suffix.size(), wanted_suffix) != 0)) continue;
    FbxStringList uv_sets;
    mesh->GetUVSetNames(uv_sets);
    if (uv_sets.GetCount() == 0) continue;
    std::cerr << "mesh=" << node->GetName() << " polygons="
              << mesh->GetPolygonCount() << " uv_sets=";
    for (int set = 0; set < uv_sets.GetCount(); ++set)
      std::cerr << (set ? "," : "") << uv_sets[set];
    std::cerr << '\n';
    const char *uv_set = uv_sets[0];
    FbxLayerElementMaterial *materials = mesh->GetElementMaterial();
    for (int polygon = 0; polygon < mesh->GetPolygonCount(); ++polygon) {
      int material = 0;
      if (materials && materials->GetIndexArray().GetCount() > polygon)
        material = materials->GetIndexArray().GetAt(polygon);
      if (material != wanted_material || mesh->GetPolygonSize(polygon) != 3) continue;
      for (int corner = 0; corner < 3; ++corner) {
        const int point_index = mesh->GetPolygonVertex(polygon, corner);
        const FbxVector4 point = mesh->GetControlPointAt(point_index);
        FbxVector2 uv; bool unmapped = false;
        mesh->GetPolygonVertexUV(polygon, corner, uv_set, uv, unmapped);
        if (!unmapped) vertices.push_back({point[0], point[1], point[2], uv[0], 1.0 - uv[1]});
      }
    }
  }
  if (vertices.empty()) {
    std::cerr << "no triangles found for material slot " << wanted_material << '\n';
    return 1;
  }
  double min_x=1e30,min_y=1e30,min_z=1e30,max_x=-1e30,max_y=-1e30,max_z=-1e30;
  for (const auto &v : vertices) {
    min_x=std::min(min_x,v.x); min_y=std::min(min_y,v.y); min_z=std::min(min_z,v.z);
    max_x=std::max(max_x,v.x); max_y=std::max(max_y,v.y); max_z=std::max(max_z,v.z);
  }
  const double cx=(min_x+max_x)/2, cy=(min_y+max_y)/2, cz=(min_z+max_z)/2;
  const double scale=2.0/std::max({max_x-min_x,max_y-min_y,max_z-min_z});
  std::ofstream out(argv[2]);
  out << std::fixed << std::setprecision(6);
  out << "{\"source\":\"" << argv[1] << "/UV0/material-slot-" << wanted_material
      << "\",\"triangleCount\":" << vertices.size()/3 << ",\"vertices\":[";
  for (size_t i=0; i<vertices.size(); ++i) {
    const auto &v=vertices[i]; if(i) out << ',';
    out << (v.x-cx)*scale << ',' << (v.y-cy)*scale << ',' << (v.z-cz)*scale << ',' << v.u << ',' << v.v;
  }
  out << "]}\n";
  std::cout << vertices.size()/3 << " triangles\n";
  manager->Destroy();
}

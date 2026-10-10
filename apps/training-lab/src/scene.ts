/**
 * The range: a dark, low-saturation hall with cover for angle-hold drills.
 * Palette rule (shared with perception): environment colors stay well below the
 * saturation of target highlight colors and the crosshair, so color masks stay clean.
 */
import * as THREE from "three";

export interface Cover {
  mesh: THREE.Mesh;
  box: THREE.Box3;
}

export interface PeekSpot {
  /** World x of the cover edge the bot emerges from. */
  edgeX: number;
  z: number;
  /** +1: emerges toward +x (from behind cover on the left), -1: toward -x. */
  dir: 1 | -1;
  groundY: number;
}

function gridTexture(): THREE.CanvasTexture {
  const size = 512;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d")!;
  g.fillStyle = "#24292e";
  g.fillRect(0, 0, size, size);
  // Subtle concrete noise
  const img = g.getImageData(0, 0, size, size);
  for (let i = 0; i < img.data.length; i += 4) {
    const n = (Math.random() - 0.5) * 10;
    img.data[i] = Math.max(0, Math.min(255, img.data[i]! + n));
    img.data[i + 1] = Math.max(0, Math.min(255, img.data[i + 1]! + n));
    img.data[i + 2] = Math.max(0, Math.min(255, img.data[i + 2]! + n));
  }
  g.putImageData(img, 0, 0);
  g.strokeStyle = "#30363c";
  g.lineWidth = 2;
  for (let i = 0; i <= size; i += 128) {
    g.beginPath();
    g.moveTo(i, 0);
    g.lineTo(i, size);
    g.moveTo(0, i);
    g.lineTo(size, i);
    g.stroke();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(20, 30);
  tex.anisotropy = 8;
  return tex;
}

function panelTexture(base: string, line: string): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 256;
  const g = c.getContext("2d")!;
  g.fillStyle = base;
  g.fillRect(0, 0, 256, 256);
  g.fillStyle = line;
  g.fillRect(0, 0, 256, 3);
  g.fillRect(0, 0, 3, 256);
  g.fillRect(0, 124, 256, 2);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

export class Range {
  readonly scene = new THREE.Scene();
  readonly covers: Cover[] = [];
  readonly peekSpots: PeekSpot[] = [];
  readonly bounds = { minX: -2.5, maxX: 2.5, minZ: -1.5, maxZ: 1.5 };

  constructor() {
    const s = this.scene;
    s.background = new THREE.Color("#0c0f12");
    s.fog = new THREE.Fog("#0c0f12", 35, 95);
    s.add(new THREE.HemisphereLight("#cfd8df", "#1a1d20", 1.2));
    const key = new THREE.DirectionalLight("#ffffff", 1.4);
    key.position.set(-8, 20, 6);
    s.add(key);

    const floor = new THREE.Mesh(new THREE.PlaneGeometry(60, 90), new THREE.MeshStandardMaterial({ map: gridTexture(), roughness: 0.95 }));
    floor.rotation.x = -Math.PI / 2;
    floor.position.set(0, 0, -35);
    s.add(floor);

    const wallTex = panelTexture("#343b42", "#2b3137");
    wallTex.repeat.set(12, 2);
    const wallMat = new THREE.MeshStandardMaterial({ map: wallTex, roughness: 0.9 });
    const back = new THREE.Mesh(new THREE.BoxGeometry(60, 9, 1), wallMat);
    back.position.set(0, 4.5, -72);
    s.add(back);
    for (const x of [-30, 30]) {
      const side = new THREE.Mesh(new THREE.BoxGeometry(1, 9, 90), wallMat);
      side.position.set(x, 4.5, -35);
      s.add(side);
    }
    const trimMat = new THREE.MeshStandardMaterial({ color: "#1d2227", roughness: 0.6 });
    for (let z = -8; z > -70; z -= 12) {
      for (const x of [-29.3, 29.3]) {
        const pillar = new THREE.Mesh(new THREE.BoxGeometry(0.6, 9, 0.6), trimMat);
        pillar.position.set(x, 4.5, z);
        s.add(pillar);
      }
    }

    // Cover: crates and wall segments at varied depths. Bots peek from their edges.
    const crateTex = panelTexture("#454d55", "#3a4148");
    crateTex.repeat.set(1, 1);
    const crateMat = new THREE.MeshStandardMaterial({ map: crateTex, roughness: 0.85 });
    const wallSegMat = new THREE.MeshStandardMaterial({ color: "#3c444c", roughness: 0.9 });
    const add = (w: number, h: number, d: number, x: number, y: number, z: number, mat: THREE.Material) => {
      const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
      m.position.set(x, y + h / 2, z);
      s.add(m);
      const box = new THREE.Box3().setFromObject(m);
      this.covers.push({ mesh: m, box });
      return box;
    };
    // Tall wall segments (head-level peeks)
    const w1 = add(4, 3.2, 0.8, -5.5, 0, -14, wallSegMat);
    const w2 = add(5, 3.2, 0.8, 6, 0, -19, wallSegMat);
    const w3 = add(3, 3.2, 0.8, -1.5, 0, -26, wallSegMat);
    // A raised platform with a wall on it (elevated head height)
    add(6, 1.0, 4, 11, 0, -30, crateMat);
    const w4 = add(2.5, 3.0, 0.8, 9.5, 1.0, -30.8, wallSegMat);
    // Crates
    add(1.6, 1.6, 1.6, 2.6, 0, -11, crateMat);
    add(1.6, 1.6, 1.6, -9, 0, -22, crateMat);
    add(1.6, 3.2, 1.6, -12, 0, -33, crateMat);

    const spot = (box: THREE.Box3, dir: 1 | -1, groundY = 0) =>
      this.peekSpots.push({ edgeX: dir === 1 ? box.max.x : box.min.x, z: box.min.z - 0.9, dir, groundY });
    spot(w1, 1);
    spot(w1, -1);
    spot(w2, -1);
    spot(w2, 1);
    spot(w3, 1);
    spot(w3, -1);
    spot(w4, -1, 1.0);
  }

  coverMeshes(): THREE.Object3D[] {
    return this.covers.map((c) => c.mesh);
  }
}

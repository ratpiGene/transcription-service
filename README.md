# Projet Fil Rouge IA Cloud : Transcript Service

_Projet M2 : "Industrialisation de l'IA dans le cloud" -> Transcription Media as a Service_

## 1. Objectif & Description
Implémenter un service de Transcription Media as a Service scalable, permettant :
- Upload vidéo / audio
- Transcription automatique via Whisper
- Génération de sous-titres
- Embedding vidéo
- Traitement asynchrone via queue
- Monitoring temps réel
- Dashboard admin
- Accélération GPU

Le projet simule une architecture de production micro-services dockerisée.

## 2. Architecture
__Composants :__
- API REST (FastAPI)
- Worker asynchrone
- Redis Queue
- Stockage objet MinIO (S3 compatible)
- Monitoring Prometheus
- Dashboard Grafana
- UI utilisateur
- GPU acceleration (CUDA)

__Flow :__
1. Upload via API
2. Stockage MinIO
3. Création job
4. Mise en queue Redis
5. Worker traite (GPU)
6. Outputs générés
7. Monitoring exposé via Prometheus 

## 3. Modèle IA
```bash
openai/whisper-base.en
```
Meilleur compromis que la version medium au niveau RAM / vitesse / précision pour l'hardware à disposition.

## 4. Prérequis
__Minimum :__
- Docker Engine
- Docker Compose
- 12Gb RAM recommandés (cumul des services)

__GPU :__
- NVIDIA GPU (fallback CPU si non détecté)
- Drivers NVIDIA à jour
- NVIDIA Container Toolkit 
> Check :
```bash
nvidia-smi
```

## 5. Installation & Lancement
> Depuis la racine du projet : 
```bash
docker compose -f docker/docker-compose.yml up -d --build
```

> Contrôle : 
```bash
docker ps
```
> Services attendus

![alt text](img/image.png)

> Stopper les services
```bash
docker compose -f docker/docker-compose.yml down
```

> Rebuild
```bash
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d --build
```

> Accès aux services : 
- Interface utilisateur : http://localhost:8000/ui
- Api Docs (swagger) : http://localhost:8000/docs
- MinIO Console : http://localhost:9001
- Prometheus : http://localhost:9090 (non verouillé)
- Grafana : http://localhost:3001 (id: admin/pw: admin)

## 6. Tests
>Tests unitaires
```bash
python -m pytest test/test_processor.py -v
```
>Tests API
```bash
python -m pytest test/test_api.py -v
```
>Tous les tests
```bash
python -m pytest test -v
```

## 7. Monitoring
Prometheus scrape :
- Job status
- Queue depth
- Job duration
- GPU utilization
- GPU memory usage
- Success / failure

Grafana dashboard auto-provisionné via :
```bash
Docker/grafana/provisioning/
```

## 8. Multi-utilisateurs
- Les jobs sont indexés par ``client_id`` (1 par navigateur)
- Isolation logique par utilisateur
- Récupération des jobs après refresh UI
- Gestion concurrente via Redis queue
- Worker configurable via MAX_CONCURRENT_JOBS
- Traitement GPU concurrent (3 jobs simultanés)
- Limitation volontaire pour éviter saturation VRAM (~8 acceptable pour ce modèle et une RTX 3050 Laptop)

## 9. Scalabilité
Le système peut évoluer via :
- Scaling horizontal du worker
- Déploiement Kubernetes
- Séparation API / Worker sur VM distinctes
- GPU dédié par worker

## 10. Limitations actuelles
- Single GPU (concurrence limitée à 3 jobs)
- Pas de rate limiting
- Pas d’auth forte
- Pas de multi-GPU orchestration
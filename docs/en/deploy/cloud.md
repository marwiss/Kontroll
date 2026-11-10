# Your own region on AWS, Azure or Google Cloud

One virtual machine in the region you choose runs the whole stack, as on
[your own server](vps-caddy.md): the API, Neo4j, Caddy with automatic HTTPS and
the nightly backup. The file [docker/cloud-init.yaml](../../../docker/cloud-init.yaml)
sets it up as the machine's user data, the same file on all three clouds. The
database, the documents and the backups stay on the machine's disk, in its
region. Dataspatium clients anywhere in the world sign in to the same server
over HTTPS.

## Before you start

- An account with the cloud and its command-line tool (`az`, `aws` or
  `gcloud`), signed in.
- A copy of `docker/cloud-init.yaml`. Set `DATAREGIUM_DOMAIN` in it to the
  server's DNS name, or leave it empty: the server is then called
  `<public address>.sslip.io`, a name that resolves to the machine's address,
  so that the certificate comes at once. `DATAREGIUM_ACME_EMAIL` is optional.
- A machine with 2 vCPU and 4 GB of memory or more (8 GB with the IFC-LPG
  module and large models), Ubuntu 24.04 LTS and a disk of 30 GB or more.
- A fixed public address, so that the name keeps pointing at the machine. Azure
  gives one with `--public-ip-sku Standard`; on AWS, attach an Elastic IP; on
  Google Cloud, reserve a static external address.

## Azure

```sh
az group create --name dataregium --location swedencentral
az vm create --resource-group dataregium --name dataregium --image Ubuntu2404 \
  --size Standard_B2s --os-disk-size-gb 30 --public-ip-sku Standard \
  --admin-username azureuser --generate-ssh-keys --custom-data cloud-init.yaml
az vm open-port --resource-group dataregium --name dataregium --port 80,443
```

## AWS

```sh
aws ec2 create-security-group --region eu-north-1 --group-name dataregium --description Dataregium
aws ec2 authorize-security-group-ingress --region eu-north-1 --group-name dataregium \
  --ip-permissions IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=0.0.0.0/0}] \
                   IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges=[{CidrIp=0.0.0.0/0}]
aws ec2 run-instances --region eu-north-1 --instance-type t3.medium --key-name <your key> \
  --image-id resolve:ssm:/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
  --security-groups dataregium --user-data file://cloud-init.yaml \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3,Encrypted=true}'
```

## Google Cloud

```sh
gcloud compute firewall-rules create dataregium-web --allow tcp:80,tcp:443 --target-tags dataregium
gcloud compute instances create dataregium --zone europe-north1-a --machine-type e2-medium \
  --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud --boot-disk-size 30GB \
  --tags dataregium --metadata-from-file user-data=cloud-init.yaml
```

The region or zone in each command decides where the data is; pick the one the
project's rules on personal data ask for.

## A few minutes later

1. The setup takes three to five minutes; `sudo tail -f /var/log/cloud-init-output.log`
   on the machine follows it. Then `https://<name>` answers. With an empty
   `DATAREGIUM_DOMAIN` the name is the public address with dashes for dots,
   such as `https://20-91-1-2.sslip.io`.
2. Read the administrator's password over SSH (`az ssh vm`, `ssh`, or
   `gcloud compute ssh`): `sudo cat /root/dataregium-admin.txt`. Sign in at
   `/signin`, change the password at `/account`, and create users and projects
   in `/admin`.
3. Register Dataspatium as a client under *Clients*, or turn on
   `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` so that it registers itself. Every
   Dataspatium, wherever it runs, then adds the server as a source and signs in
   with its own user; the server allows browser apps from any origin, with
   bearer tokens and never cookies.

## Your own name

Point a DNS `A` record at the machine's address, set `OPENCDE_PUBLIC_URL=https://<name>`
and `OPENCDE_DOMAIN=<name>` in `/opt/dataregium/.env`, and run
`sudo docker compose up -d` in `/opt/dataregium`. Caddy gets a certificate for
the new name; clients sign in again with the new address.

## Where the personal data is

- The database, the documents and the backups are Docker volumes on the
  machine's disk, in the region of its creation. Keep the disk encrypted at rest
  (the default on Azure and Google Cloud; `Encrypted=true` above on AWS).
- The backup sidecar writes a dated backup every night to a volume on the same
  disk. Copy it to object storage in the same region (S3, Blob Storage, Cloud
  Storage) for the day the machine is lost; [backup and restore](backup.md)
  says how a backup comes back.
- The server sends no telemetry. Its own connections out are the images it
  pulls (ghcr.io and docker.io), Let's Encrypt for the certificate, which sees
  the name only, and NTP for the clock check (`OPENCDE_NTP_SERVER`; empty turns
  it off). sslip.io answers DNS questions about the name, and no traffic passes
  through it; for production, use a name of your own.
- Whoever runs the server for others is the controller of what it stores; the
  README's section on personal data lists what that is.

## Updating

```sh
cd /opt/dataregium
sudo git fetch --depth 1 origin tag v<version> && sudo git checkout v<version>
sudo sed -i 's/^OPENCDE_IMAGE_TAG=.*/OPENCDE_IMAGE_TAG=<version>/' .env
sudo docker compose up -d
```

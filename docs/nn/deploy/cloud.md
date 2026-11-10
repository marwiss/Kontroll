# Din eigen region hos AWS, Azure eller Google Cloud

Éin virtuell maskin i regionen du vel, køyrer heile stakken, som på
[din eigen server](vps-caddy.md): API-et, Neo4j, Caddy med automatisk HTTPS og
den nattlege tryggingskopien. Fila [docker/cloud-init.yaml](../../../docker/cloud-init.yaml)
set han opp som brukardata for maskina, den same fila i alle tre skyane.
Databasen, dokumenta og tryggingskopiane blir på disken til maskina, i
regionen hennar. Dataspatium-klientar kvar som helst i verda loggar inn på den
same serveren over HTTPS.

## Før du byrjar

- Ein konto hos skyen og kommandolinjeverktøyet hans (`az`, `aws` eller
  `gcloud`), innlogga.
- Ein kopi av `docker/cloud-init.yaml`. Set `DATAREGIUM_DOMAIN` i han til
  DNS-namnet til serveren, eller la det stå tomt: serveren heiter då
  `<offentleg adresse>.sslip.io`, eit namn som peikar på adressa til maskina,
  slik at sertifikatet kjem med ein gong. `DATAREGIUM_ACME_EMAIL` er valfri.
- Ei maskin med 2 vCPU og 4 GB minne eller meir (8 GB med IFC-LPG-modulen og
  store modellar), Ubuntu 24.04 LTS og ein disk på 30 GB eller meir.
- Ei fast offentleg adresse, slik at namnet held fram med å peike på maskina.
  Azure gjev éi med `--public-ip-sku Standard`; hos AWS koplar du til ein
  Elastic IP; hos Google Cloud reserverer du ei statisk ekstern adresse.

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
aws ec2 run-instances --region eu-north-1 --instance-type t3.medium --key-name <nøkkelen din> \
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

Regionen eller sona i kvar kommando avgjer kvar dataa er; vel den som reglane
til prosjektet om personopplysningar krev.

## Nokre minutt seinare

1. Oppsettet tek tre til fem minutt; `sudo tail -f /var/log/cloud-init-output.log`
   på maskina følgjer det. Deretter svarar `https://<namnet>`. Med eit tomt
   `DATAREGIUM_DOMAIN` er namnet den offentlege adressa med bindestrekar i
   staden for punktum, som `https://20-91-1-2.sslip.io`.
2. Les passordet til administratoren over SSH (`az ssh vm`, `ssh` eller
   `gcloud compute ssh`): `sudo cat /root/dataregium-admin.txt`. Logg inn på
   `/signin`, byt passord på `/account`, og opprett brukarar og prosjekt i
   `/admin`.
3. Registrer Dataspatium som klient under *Klientar*, eller slå på
   `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` slik at han registrerer seg sjølv. Kvar
   Dataspatium, same kvar han køyrer, legg så til serveren som kjelde og loggar
   inn med sin eigen brukar; serveren tillèt nettappar frå alle opphav, med
   bearer-token og aldri informasjonskapslar.

## Ditt eige namn

Peik ein DNS-post av typen `A` på adressa til maskina, set `OPENCDE_PUBLIC_URL=https://<namnet>`
og `OPENCDE_DOMAIN=<namnet>` i `/opt/dataregium/.env`, og køyr
`sudo docker compose up -d` i `/opt/dataregium`. Caddy hentar eit sertifikat for
det nye namnet; klientane loggar inn att med den nye adressa.

## Kvar personopplysningane er

- Databasen, dokumenta og tryggingskopiane er Docker-volum på disken til
  maskina, i regionen der ho vart oppretta. Hald disken kryptert i kvile
  (standard hos Azure og Google Cloud; `Encrypted=true` ovanfor hos AWS).
- Tryggingskopieringa skriv ein datert kopi kvar natt til eit volum på den
  same disken. Kopier han til objektlagring i den same regionen (S3, Blob
  Storage, Cloud Storage) for dagen maskina går tapt;
  [tryggingskopiering og gjenoppretting](backup.md) seier korleis ein kopi blir
  lesen tilbake.
- Serveren sender ingen telemetri. Dei eigne sambanda hans ut er imagane han
  hentar (ghcr.io og docker.io), Let's Encrypt for sertifikatet, som berre ser
  namnet, og NTP for klokkekontrollen (`OPENCDE_NTP_SERVER`; tom slår han av).
  sslip.io svarar på DNS-spørsmål om namnet, og ingen trafikk går gjennom han;
  bruk eit eige namn i produksjon.
- Den som driv serveren for andre, er behandlingsansvarleg for det han lagrar;
  avsnittet om personopplysningar i README-en reknar opp kva det er.

## Oppdatering

```sh
cd /opt/dataregium
sudo git fetch --depth 1 origin tag v<version> && sudo git checkout v<version>
sudo sed -i 's/^OPENCDE_IMAGE_TAG=.*/OPENCDE_IMAGE_TAG=<version>/' .env
sudo docker compose up -d
```

# Din egen region hos AWS, Azure eller Google Cloud

Én virtuell maskin i regionen du velger, kjører hele stakken, som på
[din egen server](vps-caddy.md): API-et, Neo4j, Caddy med automatisk HTTPS og
den nattlige sikkerhetskopien. Filen [docker/cloud-init.yaml](../../../docker/cloud-init.yaml)
setter den opp som maskinens brukerdata, den samme filen i alle tre skyene.
Databasen, dokumentene og sikkerhetskopiene blir på maskinens disk, i dens
region. Dataspatium-klienter hvor som helst i verden logger inn på den samme
serveren over HTTPS.

## Før du begynner

- En konto hos skyen og kommandolinjeverktøyet dens (`az`, `aws` eller
  `gcloud`), innlogget.
- En kopi av `docker/cloud-init.yaml`. Sett `DATAREGIUM_DOMAIN` i den til
  serverens DNS-navn, eller la det stå tomt: serveren heter da
  `<offentlig adresse>.sslip.io`, et navn som peker på maskinens adresse, slik
  at sertifikatet kommer med en gang. `DATAREGIUM_ACME_EMAIL` er valgfri.
- En maskin med 2 vCPU og 4 GB minne eller mer (8 GB med IFC-LPG-modulen og
  store modeller), Ubuntu 24.04 LTS og en disk på 30 GB eller mer.
- En fast offentlig adresse, slik at navnet fortsetter å peke på maskinen.
  Azure gir én med `--public-ip-sku Standard`; hos AWS kobler du til en
  Elastic IP; hos Google Cloud reserverer du en statisk ekstern adresse.

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

Regionen eller sonen i hver kommando avgjør hvor dataene er; velg den som
prosjektets regler om personopplysninger krever.

## Noen minutter senere

1. Oppsettet tar tre til fem minutter; `sudo tail -f /var/log/cloud-init-output.log`
   på maskinen følger det. Deretter svarer `https://<navnet>`. Med et tomt
   `DATAREGIUM_DOMAIN` er navnet den offentlige adressen med bindestreker i
   stedet for punktum, som `https://20-91-1-2.sslip.io`.
2. Les administratorens passord over SSH (`az ssh vm`, `ssh` eller
   `gcloud compute ssh`): `sudo cat /root/dataregium-admin.txt`. Logg inn på
   `/signin`, bytt passord på `/account`, og opprett brukere og prosjekter i
   `/admin`.
3. Registrer Dataspatium som klient under *Klienter*, eller slå på
   `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` slik at den registrerer seg selv. Hver
   Dataspatium, uansett hvor den kjører, legger så til serveren som kilde og
   logger inn med sin egen bruker; serveren tillater nettapper fra alle
   opphav, med bearer-tokens og aldri informasjonskapsler.

## Ditt eget navn

Pek en DNS-post av typen `A` på maskinens adresse, sett `OPENCDE_PUBLIC_URL=https://<navnet>`
og `OPENCDE_DOMAIN=<navnet>` i `/opt/dataregium/.env`, og kjør
`sudo docker compose up -d` i `/opt/dataregium`. Caddy henter et sertifikat for
det nye navnet; klientene logger inn igjen med den nye adressen.

## Hvor personopplysningene er

- Databasen, dokumentene og sikkerhetskopiene er Docker-volumer på maskinens
  disk, i regionen der den ble opprettet. Hold disken kryptert i hvile
  (standard hos Azure og Google Cloud; `Encrypted=true` ovenfor hos AWS).
- Sikkerhetskopieringen skriver en datert kopi hver natt til et volum på den
  samme disken. Kopier den til objektlagring i den samme regionen (S3, Blob
  Storage, Cloud Storage) for dagen maskinen går tapt;
  [sikkerhetskopiering og gjenoppretting](backup.md) sier hvordan en kopi
  leses tilbake.
- Serveren sender ingen telemetri. Dens egne forbindelser ut er imagene den
  henter (ghcr.io og docker.io), Let's Encrypt for sertifikatet, som bare ser
  navnet, og NTP for klokkekontrollen (`OPENCDE_NTP_SERVER`; tom slår den av).
  sslip.io svarer på DNS-spørsmål om navnet, og ingen trafikk går gjennom den;
  bruk et eget navn i produksjon.
- Den som driver serveren for andre, er behandlingsansvarlig for det den
  lagrer; README-ens avsnitt om personopplysninger regner opp hva det er.

## Oppdatering

```sh
cd /opt/dataregium
sudo git fetch --depth 1 origin tag v<version> && sudo git checkout v<version>
sudo sed -i 's/^OPENCDE_IMAGE_TAG=.*/OPENCDE_IMAGE_TAG=<version>/' .env
sudo docker compose up -d
```

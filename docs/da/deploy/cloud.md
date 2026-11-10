# Din egen region hos AWS, Azure eller Google Cloud

Én virtuel maskine i den region, du vælger, kører hele stakken, som på
[din egen server](vps-caddy.md): API'et, Neo4j, Caddy med automatisk HTTPS og
den natlige sikkerhedskopi. Filen [docker/cloud-init.yaml](../../../docker/cloud-init.yaml)
sætter den op som maskinens brugerdata, den samme fil i alle tre skyer.
Databasen, dokumenterne og sikkerhedskopierne bliver på maskinens disk, i dens
region. Dataspatium-klienter hvor som helst i verden logger ind på den samme
server over HTTPS.

## Før du begynder

- En konto hos skyen og dens kommandolinjeværktøj (`az`, `aws` eller
  `gcloud`), logget ind.
- En kopi af `docker/cloud-init.yaml`. Sæt `DATAREGIUM_DOMAIN` i den til
  serverens DNS-navn, eller lad det være tomt: serveren hedder så
  `<offentlig adresse>.sslip.io`, et navn, der peger på maskinens adresse, så
  certifikatet kommer med det samme. `DATAREGIUM_ACME_EMAIL` er valgfri.
- En maskine med 2 vCPU og 4 GB hukommelse eller mere (8 GB med IFC-LPG-modulet
  og store modeller), Ubuntu 24.04 LTS og en disk på 30 GB eller mere.
- En fast offentlig adresse, så navnet bliver ved med at pege på maskinen.
  Azure giver én med `--public-ip-sku Standard`; hos AWS tilknytter du en
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
aws ec2 run-instances --region eu-north-1 --instance-type t3.medium --key-name <din nøgle> \
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

Regionen eller zonen i hver kommando afgør, hvor dataene er; vælg den, som
projektets regler om personoplysninger kræver.

## Nogle minutter senere

1. Opsætningen tager tre til fem minutter; `sudo tail -f /var/log/cloud-init-output.log`
   på maskinen følger den. Derefter svarer `https://<navnet>`. Med et tomt
   `DATAREGIUM_DOMAIN` er navnet den offentlige adresse med bindestreger i
   stedet for punktummer, som `https://20-91-1-2.sslip.io`.
2. Læs administratorens adgangskode over SSH (`az ssh vm`, `ssh` eller
   `gcloud compute ssh`): `sudo cat /root/dataregium-admin.txt`. Log ind på
   `/signin`, skift adgangskode på `/account`, og opret brugere og projekter i
   `/admin`.
3. Registrér Dataspatium som klient under *Klienter*, eller slå
   `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` til, så den registrerer sig selv. Hver
   Dataspatium, hvor den end kører, tilføjer så serveren som kilde og logger
   ind med sin egen bruger; serveren tillader webapps fra alle oprindelser, med
   bearer-tokens og aldrig cookies.

## Dit eget navn

Peg en DNS-post af typen `A` på maskinens adresse, sæt `OPENCDE_PUBLIC_URL=https://<navnet>`
og `OPENCDE_DOMAIN=<navnet>` i `/opt/dataregium/.env`, og kør
`sudo docker compose up -d` i `/opt/dataregium`. Caddy henter et certifikat til
det nye navn; klienterne logger ind igen med den nye adresse.

## Hvor personoplysningerne er

- Databasen, dokumenterne og sikkerhedskopierne er Docker-volumener på
  maskinens disk, i den region, hvor den blev oprettet. Hold disken krypteret i
  hvile (standard hos Azure og Google Cloud; `Encrypted=true` ovenfor hos AWS).
- Sikkerhedskopieringen skriver en dateret kopi hver nat til et volumen på den
  samme disk. Kopiér den til objektlager i den samme region (S3, Blob Storage,
  Cloud Storage) til den dag, maskinen går tabt;
  [sikkerhedskopiering og gendannelse](backup.md) fortæller, hvordan en kopi
  læses tilbage.
- Serveren sender ingen telemetri. Dens egne forbindelser ud er de images, den
  henter (ghcr.io og docker.io), Let's Encrypt til certifikatet, som kun ser
  navnet, og NTP til urkontrollen (`OPENCDE_NTP_SERVER`; tom slår den fra).
  sslip.io svarer på DNS-spørgsmål om navnet, og ingen trafik går gennem den;
  brug et eget navn i produktion.
- Den, der driver serveren for andre, er dataansvarlig for det, den gemmer;
  README'ens afsnit om personoplysninger opregner, hvad det er.

## Opdatering

```sh
cd /opt/dataregium
sudo git fetch --depth 1 origin tag v<version> && sudo git checkout v<version>
sudo sed -i 's/^OPENCDE_IMAGE_TAG=.*/OPENCDE_IMAGE_TAG=<version>/' .env
sudo docker compose up -d
```

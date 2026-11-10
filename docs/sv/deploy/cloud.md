# Den egna regionen hos AWS, Azure eller Google Cloud

En virtuell maskin i den region du väljer kör hela stacken, som på
[en egen server](vps-caddy.md): API:t, Neo4j, Caddy med automatisk HTTPS och
den nattliga säkerhetskopian. Filen [docker/cloud-init.yaml](../../../docker/cloud-init.yaml)
sätter upp den som maskinens användardata, samma fil i alla tre molnen.
Databasen, dokumenten och säkerhetskopiorna stannar på maskinens disk, i dess
region. Dataspatium-klienter var som helst i världen loggar in på samma server
över HTTPS.

## Innan du börjar

- Ett konto hos molnet och dess kommandoradsverktyg (`az`, `aws` eller
  `gcloud`), inloggat.
- En kopia av `docker/cloud-init.yaml`. Sätt `DATAREGIUM_DOMAIN` i den till
  serverns DNS-namn, eller lämna det tomt: servern heter då
  `<publik adress>.sslip.io`, ett namn som pekar på maskinens adress, så att
  certifikatet kommer direkt. `DATAREGIUM_ACME_EMAIL` är valfri.
- En maskin med 2 vCPU och 4 GB minne eller mer (8 GB med IFC-LPG-modulen och
  stora modeller), Ubuntu 24.04 LTS och en disk på 30 GB eller mer.
- En fast publik adress, så att namnet fortsätter att peka på maskinen. Azure
  ger en med `--public-ip-sku Standard`; hos AWS kopplar du en Elastic IP; hos
  Google Cloud reserverar du en statisk extern adress.

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
aws ec2 run-instances --region eu-north-1 --instance-type t3.medium --key-name <din nyckel> \
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

Regionen eller zonen i varje kommando avgör var datan finns; välj den som
projektets regler om personuppgifter kräver.

## Några minuter senare

1. Uppsättningen tar tre till fem minuter; `sudo tail -f /var/log/cloud-init-output.log`
   på maskinen följer den. Sedan svarar `https://<namnet>`. Med ett tomt
   `DATAREGIUM_DOMAIN` är namnet den publika adressen med bindestreck i stället
   för punkter, som `https://20-91-1-2.sslip.io`.
2. Läs administratörens lösenord över SSH (`az ssh vm`, `ssh` eller
   `gcloud compute ssh`): `sudo cat /root/dataregium-admin.txt`. Logga in på
   `/signin`, byt lösenord på `/account` och skapa användare och projekt i
   `/admin`.
3. Registrera Dataspatium som klient under *Klienter*, eller slå på
   `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` så att den registrerar sig själv. Varje
   Dataspatium, var den än körs, lägger sedan till servern som källa och
   loggar in med sin egen användare; servern tillåter webbappar från alla
   ursprung, med bearer-token och aldrig kakor.

## Ett eget namn

Peka en DNS-post av typen `A` på maskinens adress, sätt `OPENCDE_PUBLIC_URL=https://<namnet>`
och `OPENCDE_DOMAIN=<namnet>` i `/opt/dataregium/.env` och kör
`sudo docker compose up -d` i `/opt/dataregium`. Caddy hämtar ett certifikat
för det nya namnet; klienterna loggar in igen med den nya adressen.

## Var personuppgifterna finns

- Databasen, dokumenten och säkerhetskopiorna är Docker-volymer på maskinens
  disk, i den region där den skapades. Håll disken krypterad i vila (standard
  hos Azure och Google Cloud; `Encrypted=true` ovan hos AWS).
- Säkerhetskopieringen skriver en daterad kopia varje natt till en volym på
  samma disk. Kopiera den till objektlagring i samma region (S3, Blob Storage,
  Cloud Storage) för den dag maskinen går förlorad;
  [säkerhetskopiering och återställning](backup.md) säger hur en kopia läses
  tillbaka.
- Servern skickar ingen telemetri. Dess egna anslutningar ut är imagerna den
  hämtar (ghcr.io och docker.io), Let's Encrypt för certifikatet, som bara ser
  namnet, och NTP för klockkontrollen (`OPENCDE_NTP_SERVER`; tomt stänger av
  den). sslip.io svarar på DNS-frågor om namnet, och ingen trafik går genom
  den; i produktion, använd ett eget namn.
- Den som driver servern åt andra är personuppgiftsansvarig för det den
  lagrar; README:s avsnitt om personuppgifter räknar upp vad det är.

## Uppdatera

```sh
cd /opt/dataregium
sudo git fetch --depth 1 origin tag v<version> && sudo git checkout v<version>
sudo sed -i 's/^OPENCDE_IMAGE_TAG=.*/OPENCDE_IMAGE_TAG=<version>/' .env
sudo docker compose up -d
```

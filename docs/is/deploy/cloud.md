# Þitt eigið svæði hjá AWS, Azure eða Google Cloud

Ein sýndarvél á svæðinu sem þú velur keyrir alla stæðuna, eins og á
[eigin þjóni](vps-caddy.md): forritaskilin, Neo4j, Caddy með sjálfvirku HTTPS og
næturlega afritið. Skráin [docker/cloud-init.yaml](../../../docker/cloud-init.yaml)
setur hana upp sem notendagögn vélarinnar, sama skráin í öllum þremur skýjunum.
Gagnagrunnurinn, skjölin og afritin verða á diski vélarinnar, á svæði hennar.
Dataspatium-biðlarar hvar sem er í heiminum skrá sig inn á sama þjóninn yfir
HTTPS.

## Áður en þú byrjar

- Aðgangur að skýinu og skipanalínutól þess (`az`, `aws` eða `gcloud`),
  innskráð.
- Afrit af `docker/cloud-init.yaml`. Settu `DATAREGIUM_DOMAIN` í henni á
  DNS-nafn þjónsins, eða hafðu það autt: þjónninn heitir þá
  `<opinbert vistfang>.sslip.io`, nafn sem vísar á vistfang vélarinnar, svo að
  skírteinið kemur strax. `DATAREGIUM_ACME_EMAIL` er valfrjálst.
- Vél með 2 vCPU og 4 GB minni eða meira (8 GB með IFC-DB-einingunni og stórum
  líkönum), Ubuntu 24.04 LTS og disk upp á 30 GB eða meira.
- Fast opinbert vistfang, svo að nafnið haldi áfram að vísa á vélina. Azure
  gefur það með `--public-ip-sku Standard`; hjá AWS tengir þú Elastic IP; hjá
  Google Cloud tekur þú frá fast ytra vistfang.

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
aws ec2 run-instances --region eu-north-1 --instance-type t3.medium --key-name <lykillinn þinn> \
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

Svæðið eða svæðishlutinn í hverri skipun ræður hvar gögnin eru; veldu það sem
reglur verkefnisins um persónuupplýsingar krefjast.

## Nokkrum mínútum síðar

1. Uppsetningin tekur þrjár til fimm mínútur; `sudo tail -f /var/log/cloud-init-output.log`
   á vélinni fylgir henni. Síðan svarar `https://<nafnið>`. Með autt
   `DATAREGIUM_DOMAIN` er nafnið opinbera vistfangið með bandstrikum í stað
   punkta, eins og `https://20-91-1-2.sslip.io`.
2. Lestu lykilorð stjórnandans yfir SSH (`az ssh vm`, `ssh` eða
   `gcloud compute ssh`): `sudo cat /root/dataregium-admin.txt`. Skráðu þig inn
   á `/signin`, skiptu um lykilorð á `/account` og búðu til notendur og verkefni
   í `/admin`.
3. Skráðu Dataspatium sem biðlara undir *Biðlarar*, eða kveiktu á
   `OPENCDE_DYNAMIC_CLIENT_REGISTRATION` svo að það skrái sig sjálft. Hvert
   Dataspatium, hvar sem það keyrir, bætir þá þjóninum við sem uppsprettu og
   skráir sig inn með eigin notanda; þjónninn leyfir vefforrit frá öllum
   upprunum, með bearer-tókum og aldrei vafrakökum.

## Þitt eigið nafn

Beindu DNS-færslu af gerðinni `A` á vistfang vélarinnar, settu `OPENCDE_PUBLIC_URL=https://<nafnið>`
og `OPENCDE_DOMAIN=<nafnið>` í `/opt/dataregium/.env` og keyrðu
`sudo docker compose up -d` í `/opt/dataregium`. Caddy sækir skírteini fyrir
nýja nafnið; biðlararnir skrá sig inn aftur með nýja vistfanginu.

## Hvar persónuupplýsingarnar eru

- Gagnagrunnurinn, skjölin og afritin eru Docker-geymar á diski vélarinnar, á
  svæðinu þar sem hún var búin til. Haltu disknum dulkóðuðum í hvíld
  (sjálfgefið hjá Azure og Google Cloud; `Encrypted=true` hér að ofan hjá AWS).
- Afritunin skrifar dagsett afrit hverja nótt í geymi á sama diski. Afritaðu það
  í hlutageymslu á sama svæði (S3, Blob Storage, Cloud Storage) fyrir daginn sem
  vélin glatast; [afritun og endurheimt](backup.md) segir hvernig afrit er lesið
  til baka.
- Þjónninn sendir enga fjarmælingu. Eigin tengingar hans út eru myndirnar
  (images) sem hann sækir (ghcr.io og docker.io), Let's Encrypt fyrir
  skírteinið, sem sér aðeins nafnið, og NTP fyrir klukkuprófunina
  (`OPENCDE_NTP_SERVER`; autt slekkur á henni). sslip.io svarar DNS-fyrirspurnum
  um nafnið og engin umferð fer um það; notaðu eigið nafn í rekstri.
- Sá sem rekur þjóninn fyrir aðra er ábyrgðaraðili þess sem hann geymir; kafli
  README um persónuupplýsingar telur upp hvað það er.

## Uppfærsla

```sh
cd /opt/dataregium
sudo git fetch --depth 1 origin tag v<version> && sudo git checkout v<version>
sudo sed -i 's/^OPENCDE_IMAGE_TAG=.*/OPENCDE_IMAGE_TAG=<version>/' .env
sudo docker compose up -d
```

# Oma alue AWS:ssä, Azuressa tai Google Cloudissa

Yksi virtuaalikone valitsemallasi alueella ajaa koko pinon, kuten
[omalla palvelimella](vps-caddy.md): rajapinnan, Neo4j:n, Caddyn
automaattisella HTTPS:llä ja yöllisen varmuuskopion. Tiedosto
[docker/cloud-init.yaml](../../../docker/cloud-init.yaml) asentaa sen koneen
käyttäjädatana, sama tiedosto kaikissa kolmessa pilvessä. Tietokanta,
dokumentit ja varmuuskopiot pysyvät koneen levyllä sen alueella.
Dataspatium-asiakkaat missä päin maailmaa tahansa kirjautuvat samaan
palvelimeen HTTPS:n yli.

## Ennen kuin aloitat

- Tili pilvessä ja sen komentorivityökalu (`az`, `aws` tai `gcloud`),
  sisäänkirjautuneena.
- Kopio tiedostosta `docker/cloud-init.yaml`. Aseta siinä `DATAREGIUM_DOMAIN`
  palvelimen DNS-nimeksi tai jätä se tyhjäksi: palvelimen nimi on silloin
  `<julkinen osoite>.sslip.io`, nimi, joka osoittaa koneen osoitteeseen, joten
  varmenne saadaan heti. `DATAREGIUM_ACME_EMAIL` on valinnainen.
- Kone, jossa on vähintään 2 vCPU:ta ja 4 Gt muistia (8 Gt IFC-LPG-moduulin ja
  suurten mallien kanssa), Ubuntu 24.04 LTS ja vähintään 30 Gt:n levy.
- Kiinteä julkinen osoite, jotta nimi osoittaa edelleen koneeseen. Azure antaa
  sellaisen valinnalla `--public-ip-sku Standard`; AWS:ssä liität Elastic IP:n;
  Google Cloudissa varaat staattisen ulkoisen osoitteen.

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
aws ec2 run-instances --region eu-north-1 --instance-type t3.medium --key-name <avaimesi> \
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

Kunkin komennon alue tai vyöhyke ratkaisee, missä data on; valitse se, jota
projektin henkilötietosäännöt edellyttävät.

## Muutamaa minuuttia myöhemmin

1. Asennus kestää kolmesta viiteen minuuttia; `sudo tail -f /var/log/cloud-init-output.log`
   koneella seuraa sitä. Sen jälkeen `https://<nimi>` vastaa. Kun
   `DATAREGIUM_DOMAIN` on tyhjä, nimi on julkinen osoite, jossa pisteet on
   korvattu viivoilla, kuten `https://20-91-1-2.sslip.io`.
2. Lue ylläpitäjän salasana SSH:n yli (`az ssh vm`, `ssh` tai
   `gcloud compute ssh`): `sudo cat /root/dataregium-admin.txt`. Kirjaudu
   osoitteessa `/signin`, vaihda salasana osoitteessa `/account` ja luo
   käyttäjät ja projektit kohdassa `/admin`.
3. Rekisteröi Dataspatium asiakkaaksi kohdassa *Asiakkaat* tai ota käyttöön
   `OPENCDE_DYNAMIC_CLIENT_REGISTRATION`, jotta se rekisteröi itsensä. Jokainen
   Dataspatium, missä tahansa se toimii, lisää sitten palvelimen lähteeksi ja
   kirjautuu omalla käyttäjällään; palvelin sallii verkkosovellukset kaikista
   alkuperistä bearer-tunnisteilla, ei koskaan evästeillä.

## Oma nimi

Osoita DNS-tietue tyyppiä `A` koneen osoitteeseen, aseta `OPENCDE_PUBLIC_URL=https://<nimi>`
ja `OPENCDE_DOMAIN=<nimi>` tiedostoon `/opt/dataregium/.env` ja aja
`sudo docker compose up -d` hakemistossa `/opt/dataregium`. Caddy hakee
varmenteen uudelle nimelle; asiakkaat kirjautuvat uudelleen uudella
osoitteella.

## Missä henkilötiedot ovat

- Tietokanta, dokumentit ja varmuuskopiot ovat Docker-taltioita koneen
  levyllä, alueella, jolla kone luotiin. Pidä levy salattuna levossa
  (oletuksena Azuressa ja Google Cloudissa; `Encrypted=true` yllä AWS:ssä).
- Varmuuskopiointi kirjoittaa joka yö päivätyn kopion taltioon samalla
  levyllä. Kopioi se saman alueen objektitallennukseen (S3, Blob Storage, Cloud
  Storage) sen päivän varalle, kun kone menetetään;
  [varmuuskopiointi ja palautus](backup.md) kertoo, miten kopio luetaan
  takaisin.
- Palvelin ei lähetä telemetriaa. Sen omat yhteydet ulos ovat sen noutamat
  imaget (ghcr.io ja docker.io), Let's Encrypt varmennetta varten, joka näkee
  vain nimen, ja NTP kellon tarkistukseen (`OPENCDE_NTP_SERVER`; tyhjä poistaa
  sen käytöstä). sslip.io vastaa nimeä koskeviin DNS-kyselyihin, eikä mikään
  liikenne kulje sen kautta; käytä tuotannossa omaa nimeä.
- Se, joka ylläpitää palvelinta muille, on rekisterinpitäjä sille, mitä se
  tallentaa; README:n henkilötietoja käsittelevä kohta luettelee, mitä se on.

## Päivittäminen

```sh
cd /opt/dataregium
sudo git fetch --depth 1 origin tag v<version> && sudo git checkout v<version>
sudo sed -i 's/^OPENCDE_IMAGE_TAG=.*/OPENCDE_IMAGE_TAG=<version>/' .env
sudo docker compose up -d
```

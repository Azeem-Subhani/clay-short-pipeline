# Action tests on the 3D cast

**10856 of 10856** action x character combinations pass: 118 actions on 92 characters, each performed once in a plain test scene (three-quarter view, facing right) and measured on every frame.

| Check | Passes when |
|---|---|
| held prop | a prop that is being held is within 3 cm of the palm on every frame |
| planted feet | a foot on the ground moves less than 3.5 cm in one frame while walking (6 cm in other actions); a figure turning on the spot is exempt |
| floor | no foot is more than 4 cm below the ground (lying, kneeling, climbing and swimming actions are exempt) |
| touch | for pick_up, press, knock, turn_key, push, pull, lift, receive, open_door: the palm comes close to the thing |

Not measured: whether a pose reads, whether a hand passes through a costume, timing. Those are judged from pictures.

## Failing: none

## Per character

| Character | Pass | Fail |
|---|---|---|
| AdultMan | 118 | 0 |
| Apothecary | 118 | 0 |
| Archaeologist | 118 | 0 |
| Astronaut | 118 | 0 |
| Baby | 118 | 0 |
| Baker | 118 | 0 |
| BalletDancer | 118 | 0 |
| Barber | 118 | 0 |
| Barista | 118 | 0 |
| BeachGirl | 118 | 0 |
| Blacksmith | 118 | 0 |
| Boxer | 118 | 0 |
| Boy | 118 | 0 |
| BusDriver | 118 | 0 |
| Butler | 118 | 0 |
| Candlemaker | 118 | 0 |
| Carpenter | 118 | 0 |
| CarriageDriver | 118 | 0 |
| CasualMan | 118 | 0 |
| Chef | 118 | 0 |
| ChimneySweep | 118 | 0 |
| Cobbler | 118 | 0 |
| CourtScribe | 118 | 0 |
| DeliveryRider | 118 | 0 |
| Detective | 118 | 0 |
| Doctor | 118 | 0 |
| ElderlyWoman | 118 | 0 |
| Electrician | 118 | 0 |
| Engineer | 118 | 0 |
| Explorer | 118 | 0 |
| Farmer | 118 | 0 |
| Ferryman | 118 | 0 |
| Firefighter | 118 | 0 |
| Fisherman | 118 | 0 |
| Flapper | 118 | 0 |
| Florist | 118 | 0 |
| FootballPlayer | 118 | 0 |
| FortuneTeller | 118 | 0 |
| Gamer | 118 | 0 |
| Gardener | 118 | 0 |
| Housemaid | 118 | 0 |
| Innkeeper | 118 | 0 |
| Jester | 118 | 0 |
| Judge | 118 | 0 |
| King | 118 | 0 |
| Knight | 118 | 0 |
| Librarian | 118 | 0 |
| Lifeguard | 118 | 0 |
| LighthouseKeeper | 118 | 0 |
| Magician | 118 | 0 |
| Mechanic | 118 | 0 |
| Monk | 118 | 0 |
| Musician | 118 | 0 |
| Nobleman | 118 | 0 |
| Nurse | 118 | 0 |
| OfficeAssistant | 118 | 0 |
| OfficeMan | 118 | 0 |
| OfficeWoman | 118 | 0 |
| ParkRanger | 118 | 0 |
| Photographer | 118 | 0 |
| Pickpocket | 118 | 0 |
| Pilot | 118 | 0 |
| Pirate | 118 | 0 |
| Plumber | 118 | 0 |
| PoliceOfficer | 118 | 0 |
| Potter | 118 | 0 |
| Prince | 118 | 0 |
| Princess | 118 | 0 |
| Queen | 118 | 0 |
| Reporter | 118 | 0 |
| RoyalMessenger | 118 | 0 |
| Sailor | 118 | 0 |
| Samurai | 118 | 0 |
| Schoolgirl | 118 | 0 |
| Scientist | 118 | 0 |
| SecurityGuard | 118 | 0 |
| SeniorMan | 118 | 0 |
| Shepherd | 118 | 0 |
| Soldier | 118 | 0 |
| Stablehand | 118 | 0 |
| StreetVendor | 118 | 0 |
| Student | 118 | 0 |
| Tailor | 118 | 0 |
| Teacher | 118 | 0 |
| TownCrier | 118 | 0 |
| TrainConductor | 118 | 0 |
| Vampire | 118 | 0 |
| Veterinarian | 118 | 0 |
| VictorianPostman | 118 | 0 |
| Viking | 118 | 0 |
| Witch | 118 | 0 |
| Wizard | 118 | 0 |

## Worst measured values per action (over all characters)

| Action | Characters | Held prop gap (cm) | Foot slide (cm) | Below floor (cm) |
|---|---|---|---|---|
| `aim` | 92 | 0.0 | 0.0 | 0.0 |
| `angry` | 92 | 0.0 | 0.2 | 0.1 |
| `argue` | 92 | 0.0 | 0.3 | 0.2 |
| `beckon` | 92 | 0.0 | 0.0 | 0.0 |
| `blow` | 92 | 0.0 | 0.4 | 0.2 |
| `bow` | 92 | 0.0 | 0.0 | 0.0 |
| `carry` | 92 | 0.0 | 0.0 | 0.0 |
| `chase` | 92 | 0.0 | 2.2 | 0.0 |
| `cheer` | 92 | 0.0 | 0.4 | 1.7 |
| `clap` | 92 | 0.0 | 0.0 | 0.0 |
| `climb` | 92 | 0.0 | 0.0 | 0.0 |
| `cover_mouth` | 92 | 0.0 | 0.0 | 0.0 |
| `cower` | 92 | 0.0 | 0.4 | 0.2 |
| `crawl` | 92 | 0.0 | 0.0 | 0.0 |
| `crouch` | 92 | 0.0 | 0.8 | 0.6 |
| `cry` | 92 | 0.0 | 0.3 | 0.2 |
| `curtsy` | 92 | 0.0 | 0.0 | 0.0 |
| `dread` | 92 | 0.0 | 0.2 | 0.2 |
| `drink` | 92 | 0.0 | 0.0 | 0.0 |
| `drop` | 92 | 0.0 | 0.0 | 0.0 |
| `dust_off` | 92 | 0.0 | 0.0 | 0.0 |
| `eat` | 92 | 0.0 | 0.0 | 0.0 |
| `facepalm` | 92 | 0.0 | 0.3 | 0.6 |
| `fall` | 92 | 0.0 | 0.0 | 0.0 |
| `freeze` | 92 | 0.0 | 0.5 | 0.3 |
| `gasp` | 92 | 0.0 | 0.8 | 0.5 |
| `get_up` | 92 | 0.0 | 0.0 | 0.0 |
| `grab_person` | 92 | 0.0 | 0.0 | 0.0 |
| `hand_over` | 92 | 0.0 | 0.0 | 0.0 |
| `hands_up` | 92 | 0.0 | 0.4 | 0.2 |
| `handshake` | 92 | 0.0 | 0.0 | 0.0 |
| `hang` | 92 | 0.0 | 0.0 | 0.0 |
| `haul` | 92 | 0.0 | 1.6 | 0.3 |
| `hide` | 92 | 0.0 | 0.9 | 0.0 |
| `hold_up` | 92 | 0.0 | 0.0 | 0.0 |
| `hold_up_finger` | 92 | 0.0 | 0.3 | 0.2 |
| `hug` | 92 | 0.0 | 0.9 | 0.4 |
| `inspect` | 92 | 0.0 | 0.0 | 0.0 |
| `jeer` | 92 | 0.0 | 0.0 | 0.0 |
| `juggle` | 92 | 0.0 | 0.4 | 0.7 |
| `jump` | 92 | 0.0 | 0.9 | 1.7 |
| `kneel` | 92 | 0.0 | 0.0 | 0.0 |
| `knock` | 92 | 0.0 | 0.0 | 0.0 |
| `laugh` | 92 | 0.0 | 0.5 | 0.3 |
| `lean_on` | 92 | 0.0 | 0.0 | 0.0 |
| `lie_down` | 92 | 0.0 | 0.0 | 0.0 |
| `lift` | 92 | 0.0 | 0.5 | 1.0 |
| `light` | 92 | 0.0 | 0.0 | 0.0 |
| `listen` | 92 | 0.0 | 0.0 | 0.0 |
| `look_around` | 92 | 0.0 | 0.2 | 0.4 |
| `look_away` | 92 | 0.0 | 0.0 | 0.0 |
| `nod` | 92 | 0.0 | 0.0 | 0.0 |
| `open_door` | 92 | 0.0 | 0.0 | 0.0 |
| `pace` | 92 | 0.0 | 3.0 | 0.0 |
| `panic` | 92 | 0.0 | 0.6 | 0.3 |
| `pat_back` | 92 | 0.0 | 0.0 | 0.0 |
| `peek` | 92 | 0.0 | 0.0 | 0.0 |
| `phone` | 92 | 0.0 | 0.0 | 0.0 |
| `pick_up` | 92 | 0.0 | 0.3 | 0.6 |
| `plead` | 92 | 0.0 | 0.0 | 0.0 |
| `point` | 92 | 0.0 | 0.0 | 0.0 |
| `pour` | 92 | 0.0 | 0.0 | 0.0 |
| `press` | 92 | 0.0 | 0.2 | 0.4 |
| `proud` | 92 | 0.0 | 0.2 | 0.3 |
| `pull` | 92 | 0.0 | 0.4 | 0.7 |
| `push` | 92 | 0.0 | 0.4 | 0.7 |
| `push_person` | 92 | 0.0 | 0.0 | 0.0 |
| `put_down` | 92 | 0.0 | 0.0 | 0.0 |
| `read` | 92 | 0.0 | 0.0 | 0.0 |
| `receive` | 92 | 0.0 | 0.0 | 0.0 |
| `recoil` | 92 | 0.0 | 0.2 | 0.0 |
| `ride` | 92 | 0.0 | 5.8 | 0.5 |
| `roll` | 92 | 0.0 | 0.0 | 0.0 |
| `run` | 92 | 0.0 | 1.8 | 0.1 |
| `salute` | 92 | 0.0 | 0.4 | 0.2 |
| `shake_head` | 92 | 0.0 | 0.0 | 0.0 |
| `shout` | 92 | 0.0 | 0.5 | 0.3 |
| `show` | 92 | 0.0 | 0.0 | 0.0 |
| `shrug` | 92 | 0.0 | 0.1 | 0.2 |
| `sigh` | 92 | 0.0 | 0.1 | 0.2 |
| `sit_down` | 92 | 0.0 | 4.9 | 0.7 |
| `sit_idle` | 92 | 0.0 | 0.0 | 0.0 |
| `slam` | 92 | 0.0 | 0.6 | 1.1 |
| `slap_away` | 92 | 0.0 | 0.0 | 0.0 |
| `sleep` | 92 | 0.0 | 0.0 | 0.0 |
| `slip` | 92 | 0.0 | 0.0 | 0.0 |
| `slip_banana` | 92 | 0.0 | 0.0 | 0.0 |
| `smile` | 92 | 0.0 | 0.0 | 0.0 |
| `sneak` | 92 | 0.0 | 0.6 | 0.0 |
| `sneeze` | 92 | 0.0 | 0.6 | 1.1 |
| `sniff` | 92 | 0.0 | 0.3 | 0.2 |
| `stand_up` | 92 | 0.0 | 5.5 | 0.2 |
| `stash` | 92 | 0.0 | 0.0 | 0.0 |
| `step_forward` | 92 | 0.0 | 2.0 | 0.0 |
| `stomp` | 92 | 0.0 | 3.9 | 1.1 |
| `struggle` | 92 | 0.0 | 0.8 | 1.0 |
| `suspicious` | 92 | 0.0 | 0.0 | 0.0 |
| `swim` | 92 | 0.0 | 0.0 | 0.0 |
| `take_out` | 92 | 0.0 | 0.0 | 0.0 |
| `talk` | 92 | 0.0 | 0.0 | 0.0 |
| `tap` | 92 | 0.0 | 0.0 | 0.0 |
| `think` | 92 | 0.0 | 0.0 | 0.0 |
| `throw` | 92 | 0.0 | 0.4 | 0.7 |
| `tie` | 92 | 0.0 | 0.0 | 0.0 |
| `tip_hat` | 92 | 0.0 | 0.0 | 0.0 |
| `tiptoe` | 92 | 0.0 | 0.7 | 0.0 |
| `tremble` | 92 | 0.0 | 0.6 | 0.2 |
| `turn_around` | 92 | 0.0 | 0.1 | 1.0 |
| `turn_key` | 92 | 0.0 | 0.0 | 0.0 |
| `use_tool` | 92 | 0.0 | 0.0 | 0.0 |
| `wake_up` | 92 | 0.0 | 0.0 | 0.0 |
| `walk` | 92 | 0.0 | 2.5 | 0.0 |
| `watch` | 92 | 0.0 | 0.0 | 0.0 |
| `wave` | 92 | 0.0 | 0.0 | 0.0 |
| `whisper` | 92 | 0.0 | 0.0 | 0.0 |
| `whistle` | 92 | 0.0 | 0.0 | 0.0 |
| `write` | 92 | 0.0 | 0.0 | 0.0 |
| `yawn` | 92 | 0.0 | 0.0 | 0.0 |

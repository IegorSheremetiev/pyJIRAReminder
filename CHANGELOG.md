# Changelog

## [0.10.0](https://github.com/IegorSheremetiev/pyJIRAReminder/compare/v0.9.8...v0.10.0) (2025-11-11)


### Features

* new tests for pop-up reminders and new structure ([b0c45f1](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/b0c45f1e8fc5e2de20682fcdeb13a691e5611683))

## [0.9.8](https://github.com/IegorSheremetiev/pyJIRAReminder/compare/v0.9.7...v0.9.8) (2025-11-10)


### Reverts

* **release:** workflow reverted to generate noconsole version ([5b46950](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/5b46950c9e98f9eb26ca43a64ee94a22359725d4))

## [0.9.7](https://github.com/IegorSheremetiev/pyJIRAReminder/compare/v0.9.6...v0.9.7) (2025-11-10)


### Bug Fixes

* **cli:** Added invokation of the terminal when it is required ([7143ee4](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/7143ee4d454224daf663bd07844e503e9384c0d9))

## [0.9.6](https://github.com/IegorSheremetiev/pyJIRAReminder/compare/v0.9.5...v0.9.6) (2025-11-10)


### Bug Fixes

* **workflow:** console enable for win pyinstaller ([0703e5f](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/0703e5f29ec96a6c2864676c795db73386967771))

## [0.9.5](https://github.com/IegorSheremetiev/pyJIRAReminder/compare/v0.9.4...v0.9.5) (2025-11-09)


### Bug Fixes

* **loggign:** invoke logger intialization after checks for instances ([37c9286](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/37c9286e2a0ead3c3bb8aeb6b45cf57e593a38db))

## [0.9.4](https://github.com/IegorSheremetiev/pyJIRAReminder/compare/v0.9.3...v0.9.4) (2025-11-09)


### Bug Fixes

* --noconsole option active in pyinstaller ([a54aa61](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/a54aa618014906f95d9f6e518b02b39b7a8f7e5f))

## [0.9.3](https://github.com/IegorSheremetiev/pyJIRAReminder/compare/v0.9.2...v0.9.3) (2025-11-09)


### Bug Fixes

* release.yml generates relese version, not prerelease ([40640bf](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/40640bf6152ef3004b2bb1efd25c9659dc616514))

## [0.9.2](https://github.com/IegorSheremetiev/pyJIRAReminder/compare/v0.9.1...v0.9.2) (2025-11-09)


### Bug Fixes

* pyinstaller includes src folder for scan ([b330e5b](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/b330e5b61f840d7d4291cea95cd8f767c6cfd1cd))

## [0.9.1](https://github.com/IegorSheremetiev/pyJIRAReminder/compare/v0.9.0...v0.9.1) (2025-11-09)


### Bug Fixes

* workflow PAT is added to trigger Release workflow ([0cc4d09](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/0cc4d09254eb5011a1afd0b45f9d655a26e94f57))

## [0.9.0](https://github.com/IegorSheremetiev/pyJIRAReminder/compare/v0.8.0...v0.9.0) (2025-11-09)


### Features

* added timer with 2h tick to refresh all ([a650ee9](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/a650ee9ccc5cdb2b7bc61a0b13774447906ad21c))

## [0.8.0](https://github.com/IegorSheremetiev/pyJIRAReminder/compare/v0.7.4...v0.8.0) (2025-11-09)


### Features

* **refactor:** the monoluthic pyJIRAReminder.py is splitte on several files in ./src/jire_reminder ([c81db92](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/c81db92302adbcb7eb5990d83ed5d01c89aaad58))

## [0.7.4](https://github.com/IegorSheremetiev/pyJIRAReminder/compare/v0.7.3...v0.7.4) (2025-11-09)


### Reverts

* **ci:** release-please manifest moved back to root ([5e4199b](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/5e4199b74696a2377d05c10355c1f0dd4fdef721))
* **ci:** release-please workflow fix for manifest location ([33c0dcd](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/33c0dcd3a4ffe8a8b9b4c424ab99f68828b16877))

## [0.7.3](https://github.com/IegorSheremetiev/pyJIRAReminder/compare/v0.7.2...v0.7.3) (2025-11-09)


### Reverts

* **ci:** release-please scripts are in root ([047b2bf](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/047b2bfa99900b0567f55ebc7200b7a456348d0a))
* **ci:** release-please scripts are in root ([94c6379](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/94c6379514f20fcae9abef183474618fee4050eb))

## [0.7.2](https://github.com/IegorSheremetiev/pyJIRAReminder/compare/v0.7.1...v0.7.2) (2025-11-07)


### Bug Fixes

* application lock mechanism set ([ac7c9c7](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/ac7c9c7efdb3a639a2b7c26e170a6653c9d59971))

## [0.7.1](https://github.com/IegorSheremetiev/pyJIRAReminder/compare/v0.7.0...v0.7.1) (2025-11-07)


### Features

* card view of tasks ([67dc45b](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/67dc45b6c07df2623df5ab009b25533baf56bdf0))


### Bug Fixes

* extra logging is defined to check pyinstaller issues. Updates in workflow and TODO. ([1b30c9d](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/1b30c9d8d2e3a03ea69df8e3b8f25b68883e5450))
* icons are set for the application and build scripts are updated to use assets ([d3cb34d](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/d3cb34dba1265f2bdb3b470230bc5073b9e21517))
* jira_reminder.py was defined in the yml when pyJIRAReminder.py is required ([49f6096](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/49f60966ec0b72b2cf1496c6a82525ee0defd400))
* naming correction in the build_local scripts for main python file and app png. Logging of the encrypted file PATH ([956845c](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/956845c812a98126e1ea05d5d55b7d8b30a23c6c))
* workflow fix for the Linux built what prevents any execution, TODO.md updated as 1 bullet is closed ([ee29aaa](https://github.com/IegorSheremetiev/pyJIRAReminder/commit/ee29aaac1f83090232ca86aec35f0ba57933fa9a))
